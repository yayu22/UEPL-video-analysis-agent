import React from 'react';
import { AnalysisEntry } from '../types';

interface AnalysisLogProps {
  analysisResult: AnalysisEntry[];
  isLoading: boolean;
}

// A new sub-component for a single, styled log entry
const LogEntry: React.FC<{ entry: AnalysisEntry }> = ({ entry }) => {
  // Split timestamp into date and time for two-line display
  const timestampParts = entry.timestamp.split(' ');
  const date = timestampParts[0] || 'N/A';
  const time = timestampParts.slice(1).join(' ') || '';

  // Function to format the event name with a line break if it contains multiple words
  const formatEventName = (eventName: string) => {
    const words = eventName.split(' ');
    if (words.length > 1) {
      const halfway = Math.ceil(words.length / 2);
      return (
        <>
          {words.slice(0, halfway).join(' ')}
          <br />
          {words.slice(halfway).join(' ')}
        </>
      );
    }
    return eventName;
  };

  return (
    <div className="flex items-center space-x-4 sm:space-x-6 py-3 px-4 border-b border-gray-800 last:border-b-0 hover:bg-gray-800/50 rounded-md transition-colors duration-200">
      {/* Timestamp */}
      <div className="w-28 flex-shrink-0 font-mono text-sm text-gray-400">
        <div>{date}</div>
        <div>{time}</div>
      </div>

      {/* Event */}
      <div className="w-32 flex-shrink-0 text-red-400 font-semibold text-center leading-tight">
        {formatEventName(entry.event)}
      </div>

      {/* Confidence */}
      <div className="w-24 flex-shrink-0 flex justify-center">
         <div className="flex items-center justify-center h-10 w-20 bg-indigo-700/80 rounded-lg shadow-lg">
            <span className="text-white font-bold text-sm">{(entry.confidence * 100).toFixed(0)}%</span>
         </div>
      </div>
      
      {/* Reason */}
      <div className="flex-grow text-gray-300 text-sm">
        {entry.reason}
      </div>
    </div>
  );
};


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
    <div className="w-full bg-gray-900/70 backdrop-blur-sm p-2 sm:p-4 rounded-2xl border border-gray-700 shadow-xl mt-8">
      <h3 className="text-xl font-bold text-indigo-300 mb-2 px-4 pt-2">Analysis Log</h3>
      <div className="flex flex-col">
        {analysisResult.map((entry, index) => (
          <LogEntry key={index} entry={entry} />
        ))}
      </div>
    </div>
  );
};