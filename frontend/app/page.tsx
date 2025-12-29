'use client';

import { useState } from 'react';
import DecisionViewer from './components/DecisionViewer';
import BatchProcessor from './components/BatchProcessor';

type Tab = 'single' | 'batch';

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('single');

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
          
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('single')}
                className={`px-6 py-4 text-sm font-medium border-b-2 ${
                  activeTab === 'single'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Single Decision
              </button>
              <button
                onClick={() => setActiveTab('batch')}
                className={`px-6 py-4 text-sm font-medium border-b-2 ${
                  activeTab === 'batch'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Batch Processing
              </button>
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'single' ? <DecisionViewer /> : <BatchProcessor />}
          </div>
        </div>
      </div>
    </main>
  );
}
