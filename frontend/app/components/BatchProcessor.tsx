'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { 
  batchEvaluate, 
  getBatchStatus, 
  batchProcessFromDrive,
  getDecision,
  processFromDrive,
  DecisionResponse,
  BatchEvaluationRequest,
  BatchStatusResponse
} from '@/lib/api';
import VarianceTracker from './VarianceTracker';

const DEFAULT_DRIVE_FOLDER_ID = process.env.NEXT_PUBLIC_DRIVE_FOLDER_ID || 'YOUR_DRIVE_FOLDER_ID_HERE';

interface BatchItem {
  id: string;
  value: string;
  type: 'tracking' | 'claim_id';
  status: 'pending' | 'processing' | 'completed' | 'error';
  decision?: DecisionResponse;
  error?: string;
  source: 'db' | 'drive';
}

interface BatchProcessorProps {
  initialInput?: string;
}

export default function BatchProcessor({ initialInput = '' }: BatchProcessorProps) {
  const isDev = process.env.NODE_ENV === 'development';
  const [input, setInput] = useState(initialInput);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [processing, setProcessing] = useState(false);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchStatus, setBatchStatus] = useState<BatchStatusResponse | null>(null);
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const backendCheckController = useRef<AbortController | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const pollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const getBaseUrl = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    return apiUrl.replace('/api/v1', '');
  };
  
  useEffect(() => {
    if (initialInput) {
      setInput(initialInput);
    }
  }, [initialInput]);

  useEffect(() => {
    const checkBackend = async () => {
      backendCheckController.current?.abort();
      const controller = new AbortController();
      backendCheckController.current = controller;
      try {
        const response = await fetch(`${getBaseUrl()}/health`, {
          method: 'GET',
          signal: controller.signal,
        });
        setBackendConnected(response.ok);
      } catch (error) {
        setBackendConnected(false);
      }
    };
    checkBackend();
    const interval = setInterval(checkBackend, 30000);
    return () => {
      clearInterval(interval);
      backendCheckController.current?.abort();
    };
  }, []);

  const parseInput = useCallback((raw: string): { type: 'tracking' | 'claim_id', values: string[] | number[] } => {
    const items = raw.split(',').map(s => s.trim()).filter(Boolean);
    return { type: 'tracking', values: items };
  }, []);

  const checkClaimExists = async (trackingNumber: string): Promise<{ exists: boolean; claimId?: number; error?: string }> => {
    try {
      const decision = await getDecision(trackingNumber);
      if (isDev) {
        console.log(`[BatchProcessor] ✓ ${trackingNumber} exists in DB (Claim ID: ${decision.claim_id})`);
      }
      return { exists: true, claimId: decision.claim_id };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      if (isDev) {
        console.log(`[BatchProcessor] ✗ ${trackingNumber} check result: ${errorMessage}`);
      }
      
      if (errorMessage.includes('Failed to fetch') || errorMessage.includes('Cannot connect')) {
        if (isDev) {
          console.warn(`[BatchProcessor] Connection error for ${trackingNumber} - will try Drive processing`);
        }
        return { exists: false, error: 'Connection error - will try Drive processing' };
      }
      
      if (errorMessage.includes('No decision found') || errorMessage.includes('404')) {
        if (isDev) {
          console.log(`[BatchProcessor] ${trackingNumber} exists but no decision - will use Drive to create decision`);
        }
        return { exists: false, error: 'No decision found - will use Drive processing' };
      }
      
      return { exists: false };
    }
  };

  const processBatch = async () => {
    if (!input.trim()) {
      return;
    }

    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }

    setProcessing(true);
    const parsed = parseInput(input);
    
    const batchItems: BatchItem[] = [];
    const dbClaimIds: number[] = [];
    const driveTrackingNumbers: string[] = [];

    for (const value of parsed.values) {
      const trackingNumber = value as string;
      const itemId = `tracking-${trackingNumber}`;
      
      if (isDev) {
        console.log(`[BatchProcessor] Checking tracking number: ${trackingNumber}`);
      }
      const checkResult = await checkClaimExists(trackingNumber);
      if (isDev) {
        console.log(`[BatchProcessor] Result for ${trackingNumber}:`, checkResult);
      }
      
      if (checkResult.exists && checkResult.claimId) {
        dbClaimIds.push(checkResult.claimId);
        batchItems.push({
          id: itemId,
          value: trackingNumber,
          type: 'tracking',
          status: 'pending',
          source: 'db',
        });
        if (isDev) {
          console.log(`[BatchProcessor] ${trackingNumber} -> DB mode (Claim ID: ${checkResult.claimId})`);
        }
      } else {
        if (checkResult.error) {
          if (isDev) {
            console.warn(`[BatchProcessor] ${trackingNumber} check failed: ${checkResult.error}`);
          }
        }
        driveTrackingNumbers.push(trackingNumber);
        batchItems.push({
          id: itemId,
          value: trackingNumber,
          type: 'tracking',
          status: 'pending',
          source: 'drive',
        });
        if (isDev) {
          console.log(`[BatchProcessor] ${trackingNumber} -> Drive mode`);
        }
      }
    }
    
    if (isDev) {
      console.log(`[BatchProcessor] Summary: ${dbClaimIds.length} DB claims, ${driveTrackingNumbers.length} Drive claims`);
      console.log(`[BatchProcessor] DB claim IDs:`, dbClaimIds);
      console.log(`[BatchProcessor] Drive tracking numbers:`, driveTrackingNumbers);
    }

    setItems(batchItems);

    const updateItemStatus = (id: string, status: BatchItem['status'], decision?: DecisionResponse, error?: string) => {
      setItems(prev => prev.map(item => 
        item.id === id ? { ...item, status, decision, error } : item
      ));
    };

    const processDriveItems = async () => {
      if (driveTrackingNumbers.length === 0) return;

      // Reduced concurrency to avoid overwhelming the server
      // Each drive item processing is CPU/memory intensive (Google Drive API, OCR, etc.)
      const concurrencyLimit = 2;
      for (let i = 0; i < driveTrackingNumbers.length; i += concurrencyLimit) {
        const batch = driveTrackingNumbers.slice(i, i + concurrencyLimit);
        
        const results = await Promise.allSettled(
          batch.map(async (trackingNumber) => {
            const itemId = `tracking-${trackingNumber}`;
            updateItemStatus(itemId, 'processing');
            
            try {
              const decision = await processFromDrive({
                tracking_number: trackingNumber,
                drive_folder_id: DEFAULT_DRIVE_FOLDER_ID,
              });
              updateItemStatus(itemId, 'completed', decision);
              return decision;
            } catch (error) {
              const errorMessage = error instanceof Error ? error.message : 'Unknown error';
              // Handle timeout and connection errors gracefully
              if (error instanceof Error && (error.name === 'AbortError' || errorMessage.includes('ERR_EMPTY_RESPONSE') || errorMessage.includes('Failed to fetch'))) {
                updateItemStatus(itemId, 'error', undefined, 'Request timeout or server error - server may be overwhelmed. Try again with fewer items.');
              } else {
                updateItemStatus(itemId, 'error', undefined, errorMessage);
              }
              // Don't throw - allow other items to continue processing
            }
          })
        );
      }
    };

    const processDbItems = async () => {
      if (dbClaimIds.length === 0) return;

      const dbItems = batchItems.filter(i => i.source === 'db');
      
      for (const item of dbItems) {
        updateItemStatus(item.id, 'processing');
      }

      try {
        const batchRequest: BatchEvaluationRequest = {
          claim_ids: dbClaimIds,
        };

        const batchResponse = await batchEvaluate(batchRequest);
        setBatchId(batchResponse.batch_id);

        const pollInterval = setInterval(async () => {
          try {
            const status = await getBatchStatus(batchResponse.batch_id);
            setBatchStatus(status);

            if (status.status === 'completed' || status.status === 'failed') {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
              }
              if (pollTimeoutRef.current) {
                clearTimeout(pollTimeoutRef.current);
                pollTimeoutRef.current = null;
              }
              
              if (status.status === 'completed') {
                if (isDev) {
                  console.log(`[BatchProcessor] Batch completed, fetching decisions for ${dbItems.length} items...`);
                }
                for (const item of dbItems) {
                  try {
                    if (isDev) {
                      console.log(`[BatchProcessor] Fetching decision for ${item.value}...`);
                    }
                    const decision = await getDecision(item.value);
                    if (isDev) {
                      console.log(`[BatchProcessor] ✓ Got decision for ${item.value}:`, decision);
                    }
                    updateItemStatus(item.id, 'completed', decision);
                  } catch (error) {
                    const errorMessage = error instanceof Error ? error.message : 'Failed to fetch decision';
                    if (isDev) {
                      console.error(`[BatchProcessor] ✗ Error fetching decision for ${item.value}:`, error);
                    }
                    
                    if (errorMessage.includes('Failed to fetch') || errorMessage.includes('Cannot connect')) {
                      if (isDev) {
                        console.warn(`[BatchProcessor] Connection error for ${item.value}, trying Drive processing as fallback...`);
                      }
                      updateItemStatus(item.id, 'processing');
                      try {
                        const decision = await processFromDrive({
                          tracking_number: item.value,
                          drive_folder_id: DEFAULT_DRIVE_FOLDER_ID,
                        });
                        if (isDev) {
                          console.log(`[BatchProcessor] ✓ Fallback Drive processing succeeded for ${item.value}`);
                        }
                        setItems(prev => prev.map(i => 
                          i.id === item.id 
                            ? { ...i, status: 'completed' as const, decision, source: 'drive' as const }
                            : i
                        ));
                      } catch (driveError) {
                        const errorMessage = driveError instanceof Error ? driveError.message : 'Connection error - backend may not be running';
                        updateItemStatus(item.id, 'error', undefined, errorMessage);
                      }
                    } else if (errorMessage.includes('No decision found') || errorMessage.includes('404')) {
                      updateItemStatus(item.id, 'error', undefined, 'No decision found - batch may not have created decision yet');
                    } else {
                      updateItemStatus(item.id, 'error', undefined, errorMessage);
                    }
                  }
                }
              } else {
                const errorMsg = status.error_message || 'Batch processing failed';
                console.error(`[BatchProcessor] Batch failed: ${errorMsg}`);
                for (const item of dbItems) {
                  updateItemStatus(item.id, 'error', undefined, errorMsg);
                }
              }
            } else {
              // Batch is still processing - try to fetch decisions for items that might be done
              // This allows DB claims to display immediately as they complete
              const processedCount = status.processed_count || 0;
              const totalCount = status.claim_count || dbItems.length;
              
              // Try to fetch decisions for all items that are still processing
              // This is optimistic - if a decision exists, display it immediately
              await Promise.allSettled(
                dbItems
                  .filter(item => item.status === 'processing')
                  .map(async (item) => {
                    try {
                      const decision = await getDecision(item.value);
                      // Successfully got decision - mark as completed immediately
                      updateItemStatus(item.id, 'completed', decision);
                      if (isDev) {
                        console.log(`[BatchProcessor] ✓ Fetched decision for ${item.value} before batch completion`);
                      }
                    } catch (error) {
                      // Decision doesn't exist yet or error - that's OK, will retry next poll
                      // Don't log to avoid spam
                    }
                  })
              );
            }
          } catch (error) {
            if (isDev) {
              console.error('Error polling batch status:', error);
            }
          }
        }, 1000); // Poll every 1 second for faster updates (was 2 seconds)

        pollIntervalRef.current = pollInterval;
        pollTimeoutRef.current = setTimeout(() => {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          pollTimeoutRef.current = null;
        }, 300000);
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Failed to submit batch';
        console.error(`[BatchProcessor] Error submitting batch:`, error);
        for (const item of dbItems) {
          updateItemStatus(item.id, 'error', undefined, errorMessage);
        }
      }
    };

    // Process DB items first (faster) and Drive items in parallel
    // DB items can be displayed immediately as they complete
    try {
      await Promise.all([
        processDbItems(),  // DB claims process faster and can be displayed immediately
        processDriveItems(), // Drive items take longer (document processing, OCR, etc.)
      ]);
    } finally {
      setProcessing(false);
    }
  };

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
      }
    };
  }, []);

  const getStatusColor = (status: BatchItem['status']) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-50';
      case 'processing': return 'text-blue-600 bg-blue-50';
      case 'error': return 'text-red-600 bg-red-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const getSourceBadge = (source: 'db' | 'drive') => {
    return source === 'db' 
      ? <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">DB</span>
      : <span className="px-2 py-1 text-xs font-medium bg-purple-100 text-purple-800 rounded">Drive</span>;
  };

  return (
    <div className="space-y-6">
      {backendConnected === false && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-md">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">
                Backend Server Not Running
              </h3>
              <div className="mt-2 text-sm text-red-700">
                <p>
                  Cannot connect to backend at <code className="bg-red-100 px-1 rounded">{getBaseUrl()}</code>
                </p>
                <p className="mt-1">
                  Please start the backend server before processing batches. All operations require the backend to be running.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {backendConnected === true && (
        <div className="bg-green-50 border-l-4 border-green-500 p-4 rounded-md">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-green-800">
                Backend server is connected and ready
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Batch Processing</h2>
        
        <div className="space-y-4">
          <div>
            <label htmlFor="batch-input" className="block text-sm font-medium text-gray-700 mb-2">
              Enter tracking numbers or claim IDs (comma-separated)
            </label>
            <textarea
              id="batch-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="900, 901, 902 or 1, 2, 3"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={3}
              disabled={processing}
            />
            <p className="mt-1 text-sm text-gray-500">
              Numbers are treated as claim IDs, strings as tracking numbers. System will automatically determine if items should be processed from database or Google Drive.
            </p>
          </div>

          <button
            onClick={processBatch}
            disabled={processing || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {processing ? 'Processing...' : 'Process Batch'}
          </button>
        </div>
      </div>

      {items.length > 0 && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Processing Status</h3>
          
          {batchStatus && (
            <div className="mb-4 p-3 bg-gray-50 rounded-md">
              <p className="text-sm text-gray-700">
                Batch Status: <span className="font-medium">{batchStatus.status}</span> | 
                Processed: {batchStatus.processed_count}/{batchStatus.claim_count} | 
                Successful: {batchStatus.successful_count} | 
                Failed: {batchStatus.failed_count}
              </p>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Item</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Source</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Decision</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Amount</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                      {item.value}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm">
                      {getSourceBadge(item.source)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`px-2 py-1 text-xs font-medium rounded ${getStatusColor(item.status)}`}>
                        {item.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                      {item.decision ? (
                        <span className={`font-medium ${
                          item.decision.proposed_status === 'approve' ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {item.decision.proposed_status}
                        </span>
                      ) : item.error ? (
                        <span className="text-red-600 text-xs">{item.error}</span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                      {item.decision ? `$${item.decision.proposed_benefit_amount.toFixed(2)}` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {items.filter(i => i.status === 'completed' && i.decision).length > 0 && (
        <VarianceTracker 
          decisions={items.filter(i => i.status === 'completed' && i.decision).map(i => i.decision!)}
        />
      )}
    </div>
  );
}
