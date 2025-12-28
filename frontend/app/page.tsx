'use client';

import { useState } from 'react';
import DecisionViewer from './components/DecisionViewer';

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-4 border-b border-gray-200">
            <h1 className="text-2xl font-bold text-gray-900">
              Security Deposit Claims Decision Review
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Review and modify claim decisions by tracking number
            </p>
          </div>
          <div className="p-6">
            <DecisionViewer />
          </div>
        </div>
      </div>
    </main>
  );
}
