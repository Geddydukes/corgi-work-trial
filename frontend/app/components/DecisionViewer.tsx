'use client';

import { useState, useMemo, useCallback } from 'react';
import { getDecision, updateDecision, processFromDrive, DecisionResponse, LineItem, LineItemOverride, ProcessFromDriveRequest } from '@/lib/api';
import LineItemsList from './LineItemsList';
import DecisionSummary from './DecisionSummary';
import BatchProcessor from './BatchProcessor';

export default function DecisionViewer() {
  const [trackingNumber, setTrackingNumber] = useState('');
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lineItemStates, setLineItemStates] = useState<Map<number, { included: boolean; changed: boolean; note?: string }>>(new Map());
  const [capEnabled, setCapEnabled] = useState(true);
  const [overrideCapAmount, setOverrideCapAmount] = useState<number | undefined>(undefined);
  const [overrideStatus, setOverrideStatus] = useState<string | undefined>(undefined);
  // Default Google Drive folder ID
  const DEFAULT_DRIVE_FOLDER_ID = '1-sEEs61X3q7AG8MV6y6wlX637KLOnMs4';

  const hasCommas = useMemo(() => {
    return trackingNumber.includes(',');
  }, [trackingNumber]);

  const handleSearch = async () => {
    if (!trackingNumber.trim()) {
      setError('Please enter a tracking number');
      return;
    }

    if (hasCommas) {
      return;
    }

    setLoading(true);
    setLoadingMessage('Searching for claim...');
    setError(null);
    setSuccess(null);
    setLineItemStates(new Map());
    setCapEnabled(true);
    setOverrideCapAmount(undefined);
    setOverrideStatus(undefined);

    let processedFromDrive = false;

    try {
      console.log(`[DecisionViewer] Fetching decision for: ${trackingNumber.trim()}`);
      const startTime = Date.now();
      const result = await getDecision(trackingNumber.trim());
      const duration = Date.now() - startTime;
      console.log(`[DecisionViewer] Decision fetched in ${duration}ms:`, result);
      setLoadingMessage('');
      setDecision(result);
      
      // Initialize line item states
      const states = new Map<number, { included: boolean; changed: boolean }>();
      result.approved_line_items.forEach((_, index) => {
        states.set(index, { included: true, changed: false });
      });
      result.ineligible_line_items.forEach((_, index) => {
        states.set(result.approved_line_items.length + index, { included: false, changed: false });
      });
      setLineItemStates(states);
    } catch (err) {
      // Safely extract error message, handling objects and arrays
      let errorMessage = 'Failed to fetch decision';
      if (err instanceof Error) {
        errorMessage = err.message;
      } else if (typeof err === 'string') {
        errorMessage = err;
      } else if (Array.isArray(err)) {
        // Handle array of errors
        errorMessage = err.map(e => {
          if (typeof e === 'string') return e;
          if (e instanceof Error) return e.message;
          if (e && typeof e === 'object' && 'message' in e) return String(e.message);
          if (e && typeof e === 'object' && 'detail' in e) return String(e.detail);
          return JSON.stringify(e);
        }).join(', ');
      } else if (err && typeof err === 'object') {
        // Handle error objects - try to extract message or stringify safely
        if ('message' in err && typeof err.message === 'string') {
          errorMessage = err.message;
        } else if ('detail' in err && typeof err.detail === 'string') {
          errorMessage = err.detail;
        } else {
          try {
            errorMessage = JSON.stringify(err, null, 2);
          } catch {
            errorMessage = String(err);
          }
        }
      }
      
      console.error(`[DecisionViewer] Error fetching decision:`, err);
      
      // Handle timeout errors
      if (errorMessage.includes('timeout') || errorMessage.includes('Timeout')) {
        setLoadingMessage('');
        setError('Request timed out. The server took too long to respond. Please try again.');
        setDecision(null);
        setLoading(false);
        return;
      }
      
      // Handle connection errors
      if (errorMessage.includes('Cannot connect') || errorMessage.includes('Failed to fetch')) {
        setLoadingMessage('');
        setError('Cannot connect to the server. Please make sure the backend is running on http://localhost:8000');
        setDecision(null);
        setLoading(false);
        return;
      }
      
      // If claim not found, automatically process from Google Drive
      if (errorMessage.includes('No decision found') || errorMessage.includes('404')) {
        setError(null);
        setLoadingMessage('Claim not found. Processing from Google Drive...');
        processedFromDrive = true;
        // Automatically trigger Google Drive processing
        // Note: handleProcessFromDrive manages its own loading state
        try {
          await handleProcessFromDrive(trackingNumber.trim(), DEFAULT_DRIVE_FOLDER_ID);
        } catch (driveErr) {
          // Error already handled in handleProcessFromDrive
        }
        // Don't set loading false here - handleProcessFromDrive manages it
        return;
      } else {
        setLoadingMessage('');
        setError(errorMessage);
        setDecision(null);
      }
    } finally {
      // Only set loading false if we didn't process from drive
      // (handleProcessFromDrive manages its own loading state)
      if (!processedFromDrive) {
        setLoading(false);
      }
    }
  };

  const handleProcessFromDrive = async (trackingNum?: string, folderId?: string) => {
    const tn = trackingNum || trackingNumber.trim();
    const fid = folderId || DEFAULT_DRIVE_FOLDER_ID;

    if (!tn) {
      setError('Tracking number is required');
      return;
    }

    setLoading(true);
    setLoadingMessage('Fetching documents from Google Drive...');
    setError(null);
    setSuccess(null);
    setLineItemStates(new Map());
    setCapEnabled(true);
    setOverrideCapAmount(undefined);
    setOverrideStatus(undefined);

    try {
      const request: ProcessFromDriveRequest = {
        tracking_number: tn,
        drive_folder_id: fid,
      };

      setLoadingMessage('Downloading documents from Google Drive...');
      const result = await processFromDrive(request);
      setLoadingMessage('Generating decision...');
      
      setDecision(result);
      setLoadingMessage('');
      setSuccess(`Successfully processed claim ${tn} from Google Drive!`);
      
      // Initialize line item states
      const states = new Map<number, { included: boolean; changed: boolean }>();
      result.approved_line_items.forEach((_, index) => {
        states.set(index, { included: true, changed: false });
      });
      result.ineligible_line_items.forEach((_, index) => {
        states.set(result.approved_line_items.length + index, { included: false, changed: false });
      });
      setLineItemStates(states);
    } catch (err) {
      setLoadingMessage('');
      setError(err instanceof Error ? err.message : 'Failed to process from Google Drive');
      setDecision(null);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleLineItem = (index: number, included: boolean) => {
    const currentState = lineItemStates.get(index);
    const wasOriginallyIncluded = decision 
      ? index < decision.approved_line_items.length
      : false;
    
    const changed = included !== wasOriginallyIncluded;
    
    setLineItemStates(prev => {
      const next = new Map(prev);
      next.set(index, { 
        included, 
        changed,
        note: changed ? (next.get(index)?.note || '') : undefined
      });
      return next;
    });
  };

  const handleNoteChange = (index: number, note: string) => {
    setLineItemStates(prev => {
      const next = new Map(prev);
      const current = next.get(index);
      if (current) {
        next.set(index, { ...current, note });
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!decision) return;

    const changedItems = Array.from(lineItemStates.entries())
      .filter(([_, state]) => state.changed);
    
      const capChanged = !capEnabled || overrideCapAmount !== undefined || 
      (decision.cap_amount && capEnabled !== true);
    const statusChanged = overrideStatus !== undefined && overrideStatus !== decision.proposed_status;

    if (changedItems.length === 0 && !capChanged && !statusChanged) {
      setError('No changes to save');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const allItems: (LineItem & { originalIndex: number; originallyIncluded: boolean })[] = [
        ...decision.approved_line_items.map((item, idx) => ({
          ...item,
          originalIndex: idx,
          originallyIncluded: true,
        })),
        ...decision.ineligible_line_items.map((item, idx) => ({
          ...item,
          originalIndex: decision.approved_line_items.length + idx,
          originallyIncluded: false,
        })),
      ];

      const approvedOverrides: LineItemOverride[] = [];
      const ineligibleOverrides: LineItemOverride[] = [];

      allItems.forEach((item) => {
        const state = lineItemStates.get(item.originalIndex);
        const isIncluded = state?.included ?? item.originallyIncluded;
        const note = state?.note;

        const override: LineItemOverride = {
          line_item_index: item.originalIndex,
          user_should_be_included: isIncluded,
          user_reasoning: note || undefined,
        };

        if (isIncluded) {
          approvedOverrides.push(override);
        } else {
          ineligibleOverrides.push(override);
        }
      });

      const updated = await updateDecision(decision.tracking_number, decision.decision_id, {
        approved_line_items: approvedOverrides,
        ineligible_line_items: ineligibleOverrides,
        override_cap_amount: overrideCapAmount,
        cap_enabled: capEnabled,
        override_status: overrideStatus,
      });

      setDecision(updated);
      setSuccess(`Decision updated successfully! New approved amount: $${updated.proposed_benefit_amount.toFixed(2)}`);
      
      // Reset changed flags and overrides
      setLineItemStates(prev => {
        const next = new Map(prev);
        next.forEach((state, index) => {
          if (state.changed) {
            next.set(index, { ...state, changed: false });
          }
        });
        return next;
      });
      setOverrideStatus(undefined);
      setOverrideCapAmount(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update decision');
    } finally {
      setSubmitting(false);
    }
  };

  const liveTotal = useMemo(() => {
    if (!decision) return 0;

    let total = 0;
    const allItems = [...decision.approved_line_items, ...decision.ineligible_line_items];

    // Calculate total from all items based on their current state
    allItems.forEach((item, index) => {
      const state = lineItemStates.get(index);
      const isIncluded = state?.included ?? (index < decision.approved_line_items.length);
      if (isIncluded) {
        total += item.amount;
      }
    });

    // Apply cap if enabled
    if (capEnabled) {
      const effectiveCap = overrideCapAmount ?? decision.cap_amount;
      if (effectiveCap !== undefined && total > effectiveCap) {
        return effectiveCap;
      }
    }

    return total;
  }, [decision, lineItemStates, capEnabled, overrideCapAmount]);

  const hasChanges = useMemo(() => {
    return Array.from(lineItemStates.values()).some(state => state.changed) ||
      !capEnabled || overrideCapAmount !== undefined ||
      (overrideStatus !== undefined && overrideStatus !== decision?.proposed_status);
  }, [lineItemStates, capEnabled, overrideCapAmount, overrideStatus, decision]);

  return (
    <div className="space-y-6">
      {/* Search Form */}
      <div className="flex gap-4">
        <div className="flex-1">
          <label htmlFor="tracking-number" className="block text-sm font-medium text-gray-700 mb-2">
            Tracking Number
          </label>
          <input
            id="tracking-number"
            type="text"
            value={trackingNumber}
            onChange={(e) => setTrackingNumber(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !hasCommas && handleSearch()}
            placeholder="Enter tracking number (e.g., 901) or comma-separated list (e.g., 901, 555, 603)"
            className="w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
          />
          {hasCommas && (
            <p className="mt-2 text-sm text-blue-600">
              Batch processing will be used for multiple tracking numbers.
            </p>
          )}
        </div>
        <div className="flex items-end">
          <button
            onClick={handleSearch}
            disabled={loading || hasCommas}
            className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                <span>Processing...</span>
              </>
            ) : (
              'Search'
            )}
          </button>
        </div>
      </div>

      {hasCommas && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800 mb-4">
            <strong>Batch mode detected:</strong> Comma-separated input detected. Batch processing will be used.
          </p>
          <BatchProcessor initialInput={trackingNumber} />
        </div>
      )}

      {/* Loading Animation */}
      {loading && (
        <div className="p-6 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center gap-4">
            <div className="flex-shrink-0">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-blue-900">
                {loadingMessage || 'Loading...'}
              </p>
              {loadingMessage && (
                <p className="text-xs text-blue-700 mt-1">
                  This may take a few moments...
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Error/Success Messages */}
      {error && !loading && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {success && !loading && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-md">
          <p className="text-sm text-green-800">{success}</p>
        </div>
      )}


      {/* Decision Display */}
      {decision && (
        <div className="space-y-6">
          <DecisionSummary 
            decision={decision} 
            liveTotal={liveTotal}
            hasChanges={hasChanges}
            capEnabled={capEnabled}
            overrideCapAmount={overrideCapAmount}
            overrideStatus={overrideStatus}
            onCapEnabledChange={setCapEnabled}
            onCapAmountChange={setOverrideCapAmount}
            onStatusOverrideChange={setOverrideStatus}
          />

          <LineItemsList
            decision={decision}
            lineItemStates={lineItemStates}
            onToggle={handleToggleLineItem}
            onNoteChange={handleNoteChange}
            liveTotal={liveTotal}
          />

          {hasChanges && (
            <div className="flex justify-end pt-4 border-t border-gray-200">
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {submitting ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

