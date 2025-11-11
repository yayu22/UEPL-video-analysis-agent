import React from 'react';
import { AnalysisEntry } from '../types';

interface AnalysisLogProps {
  analysisResult: AnalysisEntry[];
  isLoading: boolean;
}

export const AnalysisLog: React.FC<AnalysisLogProps> = ({ analysisResult, isLoading }) => {
  if (isLoading) {
    return (
        <div className="w-full bg-gray-800/50 backdrop-blur-sm p-6 rounded-2xl border border-gray-700 shadow-xl mt-8">
            <h3 className="text-xl font-bold text-indigo-300 mb-4">Analysis Log</h3>
            <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="animate-pulse flex space-x-4">
                        <div className="flex-1 space-y-3 py-1">
                            <div className="h-4 bg-gray-700 rounded w-3/4"></div>
                            <div className="h-3 bg-gray-700 rounded w-1/2"></div>
                        </div>
                    </div>
                ))}
            </div>
      </div>
    );
  }

  if (analysisResult.length === 0) {
    return null;
  }
  
  return (
    <div className="w-full bg-gray-800/50 backdrop-blur-sm p-6 rounded-2xl border border-gray-700 shadow-xl mt-8">
      <h3 className="text-xl font-bold text-indigo-300 mb-4">Analysis Log</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-300">
          <thead className="text-xs text-indigo-300 uppercase bg-gray-900/50">
            <tr>
              <th scope="col" className="px-4 py-3">Time</th>
              <th scope="col" className="px-4 py-3">Event</th>
              <th scope="col" className="px-4 py-3">Confidence</th>
              <th scope="col" className="px-4 py-3">Reason</th>
            </tr>
          </thead>
          <tbody>
            {analysisResult.map((entry, index) => (
              <tr key={index} className="border-b border-gray-700 hover:bg-gray-800/60">
                <td className="px-4 py-3 font-mono">{entry.timestamp}</td>
                <td className="px-4 py-3 font-semibold text-red-400">{entry.event}</td>
                <td className="px-4 py-3">
                  <span className="bg-indigo-900 text-indigo-300 text-xs font-medium px-2 py-1 rounded-full">
                    {(entry.confidence * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400">{entry.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};