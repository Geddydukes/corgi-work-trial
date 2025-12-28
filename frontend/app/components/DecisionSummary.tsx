'use client';

import { DecisionResponse } from '@/lib/api';

interface DecisionSummaryProps {
  decision: DecisionResponse;
  liveTotal: number;
  hasChanges: boolean;
  capEnabled: boolean;
  overrideCapAmount?: number;
  overrideStatus?: string;
  onCapEnabledChange: (enabled: boolean) => void;
  onCapAmountChange: (amount?: number) => void;
  onStatusOverrideChange: (status?: string) => void;
}

function getCapReasonText(reason?: string, claimAmount?: number, maxBenefit?: number): string {
  if (!reason) return '';
  
  switch (reason) {
    case 'claim_amount':
      return `Claim Amount ($${claimAmount?.toFixed(2)})`;
    case 'max_benefit':
      return `Max Benefit ($${maxBenefit?.toFixed(2)})`;
    case 'invoice_total':
      return 'Invoice Total';
    case 'claim_amount_and_max_benefit':
      return `Claim Amount ($${claimAmount?.toFixed(2)}) and Max Benefit ($${maxBenefit?.toFixed(2)})`;
    default:
      return reason;
  }
}

export default function DecisionSummary({ 
  decision, 
  liveTotal, 
  hasChanges,
  capEnabled,
  overrideCapAmount,
  overrideStatus,
  onCapEnabledChange,
  onCapAmountChange,
  onStatusOverrideChange
}: DecisionSummaryProps) {
  const effectiveCap = overrideCapAmount ?? decision.cap_amount;
  const capReasonText = getCapReasonText(decision.cap_reason, decision.claim_amount, decision.max_benefit);
  
  return (
    <div className="bg-gray-50 rounded-lg p-6 space-y-4">
      <h2 className="text-xl font-semibold text-gray-900">Decision Summary</h2>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-sm text-gray-500">Tracking Number</p>
          <p className="text-lg font-medium text-gray-900">{decision.tracking_number}</p>
        </div>
        
        <div>
          <p className="text-sm text-gray-500">Status</p>
          <div className="flex items-center gap-2">
            <p className={`text-lg font-medium ${
              (overrideStatus || decision.proposed_status) === 'approve' ? 'text-green-600' : 'text-red-600'
            }`}>
              {(overrideStatus || decision.proposed_status).toUpperCase()}
            </p>
            {decision.proposed_status === 'deny' && (
              <button
                type="button"
                onClick={() => onStatusOverrideChange(overrideStatus === 'approve' ? undefined : 'approve')}
                className={`text-xs px-2 py-1 rounded ${
                  overrideStatus === 'approve'
                    ? 'bg-green-100 text-green-700 border border-green-300'
                    : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'
                }`}
                title="Override status to Approve"
              >
                {overrideStatus === 'approve' ? '✓ Overridden' : 'Override to Approve'}
              </button>
            )}
          </div>
          {overrideStatus && overrideStatus !== decision.proposed_status && (
            <p className="text-xs text-gray-500 mt-1">
              Original: {decision.proposed_status.toUpperCase()}
            </p>
          )}
        </div>
        
        <div>
          <p className="text-sm text-gray-500">
            {hasChanges ? 'New Approved Amount' : 'Approved Amount'}
          </p>
          <p className={`text-lg font-medium ${
            hasChanges ? 'text-blue-600' : 'text-gray-900'
          }`}>
            ${liveTotal.toFixed(2)}
          </p>
          {hasChanges && decision.proposed_benefit_amount !== liveTotal && (
            <p className="text-xs text-gray-500">
              Original: ${decision.proposed_benefit_amount.toFixed(2)}
            </p>
          )}
        </div>
        
        <div>
          <p className="text-sm text-gray-500">Invoice Total</p>
          <p className="text-lg font-medium text-gray-900">${decision.invoice_total.toFixed(2)}</p>
        </div>
      </div>

      {decision.cap_amount && (
        <div className="pt-2 border-t border-gray-200 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm text-gray-500">Cap Amount:</p>
                <span className="font-medium text-gray-900">
                  ${effectiveCap?.toFixed(2) ?? 'N/A'}
                </span>
                {capReasonText && (
                  <span className="text-xs text-gray-500">
                    (limited by {capReasonText})
                  </span>
                )}
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={capEnabled}
                onChange={(e) => onCapEnabledChange(e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <span className="text-sm text-gray-700">Apply Cap</span>
            </label>
          </div>
          
          {capEnabled && (
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-700">Override Cap:</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={overrideCapAmount ?? ''}
                onChange={(e) => {
                  const val = e.target.value;
                  onCapAmountChange(val ? parseFloat(val) : undefined);
                }}
                placeholder={decision.cap_amount?.toFixed(2)}
                className="px-3 py-1 border border-gray-300 rounded-md text-sm w-32 focus:ring-blue-500 focus:border-blue-500"
              />
              <button
                type="button"
                onClick={() => onCapAmountChange(undefined)}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Reset
              </button>
            </div>
          )}
        </div>
      )}

      {decision.flags.critical.length > 0 && (
        <div className="pt-2 border-t border-gray-200">
          <p className="text-sm font-medium text-red-600 mb-1">Critical Flags:</p>
          <ul className="list-disc list-inside text-sm text-red-600">
            {decision.flags.critical.map((flag, i) => (
              <li key={i}>{flag}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

