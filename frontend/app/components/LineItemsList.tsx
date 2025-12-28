'use client';

import { DecisionResponse, LineItem } from '@/lib/api';
import { useState } from 'react';

interface LineItemsListProps {
  decision: DecisionResponse;
  lineItemStates: Map<number, { included: boolean; changed: boolean; note?: string }>;
  onToggle: (index: number, included: boolean) => void;
  onNoteChange: (index: number, note: string) => void;
  liveTotal: number;
}

export default function LineItemsList({
  decision,
  lineItemStates,
  onToggle,
  onNoteChange,
  liveTotal,
}: LineItemsListProps) {

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

  const handleToggle = (index: number) => {
    const currentState = lineItemStates.get(index);
    if (currentState) {
      onToggle(index, !currentState.included);
    }
  };

  const changedCount = Array.from(lineItemStates.values()).filter(s => s.changed).length;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Line Items</h2>
          {changedCount > 0 && (
            <p className="text-sm text-blue-600 mt-1">
              {changedCount} item{changedCount !== 1 ? 's' : ''} changed
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-500">Total Approved</p>
          <p className="text-2xl font-bold text-blue-600">${liveTotal.toFixed(2)}</p>
        </div>
      </div>

      <div className="space-y-2">
        {allItems.map((item, displayIndex) => {
          const state = lineItemStates.get(item.originalIndex);
          const isIncluded = state?.included ?? item.originallyIncluded;
          const isChanged = state?.changed ?? false;

          return (
            <div
              key={displayIndex}
              className={`border rounded-lg p-4 ${
                isIncluded
                  ? 'bg-green-50 border-green-200'
                  : 'bg-gray-50 border-gray-200'
              } ${isChanged ? 'ring-2 ring-blue-400' : ''}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isIncluded}
                        onChange={() => handleToggle(item.originalIndex)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                      <span className="ml-3 text-sm font-medium text-gray-700">
                        {isIncluded ? 'Included' : 'Excluded'}
                      </span>
                    </label>
                    {isChanged && (
                      <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
                        Changed
                      </span>
                    )}
                    {!item.originallyIncluded && isIncluded && (
                      <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded">
                        Added
                      </span>
                    )}
                    {item.originallyIncluded && !isIncluded && (
                      <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded">
                        Removed
                      </span>
                    )}
                  </div>

                  <div className="mt-2">
                    <p className="font-medium text-gray-900">{item.description}</p>
                    <p className="text-lg font-semibold text-gray-900 mt-1">
                      ${item.amount.toFixed(2)}
                    </p>
                    {item.reason && (
                      <p className="text-sm text-gray-600 mt-1">{item.reason}</p>
                    )}
                  </div>

                  {isChanged && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Note (optional):
                      </label>
                      <textarea
                        value={state?.note || ''}
                        onChange={(e) => onNoteChange(item.originalIndex, e.target.value)}
                        placeholder="Add a note explaining this change..."
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                        rows={2}
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {allItems.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No line items found for this claim.
        </div>
      )}

      {allItems.length > 0 && (
        <div className="pt-4 border-t border-gray-300 mt-6">
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Line Items Summary</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-gray-500">Total Line Items</p>
                <p className="text-lg font-semibold text-gray-900">
                  {allItems.length}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Total Amount (All Items)</p>
                <p className="text-lg font-semibold text-gray-900">
                  ${allItems.reduce((sum, item) => sum + item.amount, 0).toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Included Items</p>
                <p className="text-lg font-semibold text-green-600">
                  {allItems.filter((item, idx) => {
                    const state = lineItemStates.get(item.originalIndex);
                    return (state?.included ?? item.originallyIncluded);
                  }).length}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Excluded Items</p>
                <p className="text-lg font-semibold text-gray-600">
                  {allItems.filter((item, idx) => {
                    const state = lineItemStates.get(item.originalIndex);
                    return !(state?.included ?? item.originallyIncluded);
                  }).length}
                </p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <p className="text-sm font-medium text-gray-700">Total Approved Amount:</p>
                <p className="text-xl font-bold text-blue-600">${liveTotal.toFixed(2)}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

