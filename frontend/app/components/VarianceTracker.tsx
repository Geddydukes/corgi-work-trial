'use client';

import { useState, useEffect, useMemo } from 'react';
import { DecisionResponse, getVarianceData, VarianceData } from '@/lib/api';

interface VarianceTrackerProps {
  decisions: DecisionResponse[];
}

export default function VarianceTracker({ decisions }: VarianceTrackerProps) {
  const [varianceData, setVarianceData] = useState<Map<string, VarianceData | null>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchVarianceData = async () => {
      setLoading(true);
      const varianceMap = new Map<string, VarianceData | null>();

      for (const decision of decisions) {
        try {
          const variance = await getVarianceData(decision.tracking_number);
          varianceMap.set(decision.tracking_number, variance);
        } catch (error) {
          console.error(`Error fetching variance for ${decision.tracking_number}:`, error);
          varianceMap.set(decision.tracking_number, null);
        }
      }

      setVarianceData(varianceMap);
      setLoading(false);
    };

    if (decisions.length > 0) {
      fetchVarianceData();
    }
  }, [decisions]);

  const aggregateMetrics = useMemo(() => {
    const withActual = Array.from(varianceData.values()).filter(v => v?.has_actual);
    
    if (withActual.length === 0) {
      return null;
    }

    const statusMatches = withActual.filter(v => v!.status_match).length;
    const statusAccuracy = (statusMatches / withActual.length) * 100;

    const mae = withActual.reduce((sum, v) => sum + Math.abs(v!.amount_variance), 0) / withActual.length;
    
    const avgPercentageError = withActual.reduce((sum, v) => {
      const absPercent = Math.abs(v!.percentage_variance);
      return sum + absPercent;
    }, 0) / withActual.length;

    return {
      statusAccuracy,
      mae,
      avgPercentageError,
      totalWithActual: withActual.length,
      totalDecisions: decisions.length,
    };
  }, [varianceData, decisions]);

  const getVarianceColor = (variance: VarianceData | null) => {
    if (!variance || !variance.has_actual) {
      return 'text-gray-500';
    }

    if (variance.status_match && Math.abs(variance.amount_variance) < 1) {
      return 'text-green-600';
    }

    const absPercent = Math.abs(variance.percentage_variance);
    if (absPercent < 10) {
      return 'text-yellow-600';
    }

    return 'text-red-600';
  };

  const getVarianceBadge = (variance: VarianceData | null) => {
    if (!variance || !variance.has_actual) {
      return <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded">No Actual</span>;
    }

    if (variance.status_match && Math.abs(variance.amount_variance) < 1) {
      return <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded">Match</span>;
    }

    const absPercent = Math.abs(variance.percentage_variance);
    if (absPercent < 10) {
      return <span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded">Small Variance</span>;
    }

    return <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded">Large Variance</span>;
  };

  if (decisions.length === 0) {
    return null;
  }

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Variance Analysis</h3>

      {loading && (
        <div className="text-center py-4 text-gray-500">Loading variance data...</div>
      )}

      {!loading && aggregateMetrics && (
        <div className="mb-6 grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="text-sm text-gray-600">Status Accuracy</p>
            <p className="text-2xl font-bold text-blue-600">{aggregateMetrics.statusAccuracy.toFixed(1)}%</p>
            <p className="text-xs text-gray-500 mt-1">
              {aggregateMetrics.totalWithActual} of {aggregateMetrics.totalDecisions} with actual data
            </p>
          </div>
          <div className="bg-purple-50 p-4 rounded-lg">
            <p className="text-sm text-gray-600">Mean Absolute Error</p>
            <p className="text-2xl font-bold text-purple-600">${aggregateMetrics.mae.toFixed(2)}</p>
          </div>
          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="text-sm text-gray-600">Avg % Error</p>
            <p className="text-2xl font-bold text-orange-600">{aggregateMetrics.avgPercentageError.toFixed(1)}%</p>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <p className="text-sm text-gray-600">Total Decisions</p>
            <p className="text-2xl font-bold text-green-600">{aggregateMetrics.totalDecisions}</p>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tracking #</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Proposed</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actual</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status Match</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Amount Variance</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">% Variance</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Variance</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {decisions.map((decision) => {
              const variance = varianceData.get(decision.tracking_number);
              return (
                <tr key={decision.tracking_number}>
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                    {decision.tracking_number}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm">
                    <div>
                      <span className={`font-medium ${
                        decision.proposed_status === 'approve' ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {decision.proposed_status}
                      </span>
                      <div className="text-gray-500">${decision.proposed_benefit_amount.toFixed(2)}</div>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm">
                    {variance?.has_actual ? (
                      <div>
                        <span className={`font-medium ${
                          variance.actual_status === 'approve' ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {variance.actual_status}
                        </span>
                        <div className="text-gray-500">${variance.actual_amount?.toFixed(2)}</div>
                      </div>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm">
                    {variance?.has_actual ? (
                      <span className={`font-medium ${
                        variance.status_match ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {variance.status_match ? '✓' : '✗'}
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium ${getVarianceColor(variance)}`}>
                    {variance?.has_actual ? (
                      variance.amount_variance >= 0 
                        ? `+$${variance.amount_variance.toFixed(2)}`
                        : `-$${Math.abs(variance.amount_variance).toFixed(2)}`
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium ${getVarianceColor(variance)}`}>
                    {variance?.has_actual ? (
                      `${variance.percentage_variance >= 0 ? '+' : ''}${variance.percentage_variance.toFixed(1)}%`
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm">
                    {getVarianceBadge(variance)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}



