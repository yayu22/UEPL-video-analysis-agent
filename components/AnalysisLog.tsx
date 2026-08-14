import React from 'react';
import { BehaviourEvent } from '../types';
import { SEVERITY_COLORS } from '../constants';

interface AnalysisLogProps {
  events: BehaviourEvent[];
  isLoading: boolean;
  onSeek?: (seconds: number) => void;
}

const SeverityPill: React.FC<{ severity: string }> = ({ severity }) => {
  const color = SEVERITY_COLORS[severity] ?? 'text-gray-300';
  const bg =
    severity === 'high' ? 'bg-red-500/15 border-red-600'
    : severity === 'medium' ? 'bg-amber-500/15 border-amber-600'
    : 'bg-yellow-500/15 border-yellow-600';
  return (
    <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${bg} ${color}`}>
      {severity}
    </span>
  );
};

const LogEntry: React.FC<{ entry: BehaviourEvent; onSeek?: (s: number) => void }> = ({ entry, onSeek }) => {
  const canSeek = typeof entry.start_s === 'number' && !!onSeek;
  return (
    <div
      onClick={() => canSeek && onSeek!(entry.start_s)}
      className={`flex items-start gap-4 py-3 px-4 border-b border-gray-800 last:border-b-0 transition-colors duration-150 ${
        canSeek ? 'cursor-pointer hover:bg-gray-800/60' : ''
      }`}
      title={canSeek ? `Jump to ${entry.start_s}s` : undefined}
    >
      {/* Time */}
      <div className="w-24 flex-shrink-0 font-mono text-xs text-gray-400 pt-0.5">
        <div className="text-gray-300">{entry.timestamp || 'n/a'}</div>
        <div className="text-indigo-400">{canSeek ? `▶ ${entry.start_s.toFixed(0)}s` : ''}</div>
      </div>

      {/* Category + severity */}
      <div className="w-40 flex-shrink-0">
        <div className="text-red-300 font-semibold text-sm leading-tight">{entry.category}</div>
        <div className="mt-1 flex items-center gap-2">
          <SeverityPill severity={entry.severity} />
          <span className="text-xs text-gray-500">{Math.round((entry.confidence ?? 0) * 100)}%</span>
        </div>
      </div>

      {/* Reason */}
      <div className="flex-grow text-gray-300 text-sm">
        {entry.reason}
        {entry.speed_kmh != null && (
          <span className="ml-2 text-xs text-gray-500">({entry.speed_kmh} km/h)</span>
        )}
      </div>
    </div>
  );
};

export const AnalysisLog: React.FC<AnalysisLogProps> = ({ events, isLoading, onSeek }) => {
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

  return (
    <div className="w-full bg-gray-900/70 backdrop-blur-sm p-2 sm:p-4 rounded-2xl border border-gray-700 shadow-xl mt-8">
      <h3 className="text-xl font-bold text-indigo-300 mb-2 px-4 pt-2">
        Analysis Log <span className="text-sm font-normal text-gray-500">({events.length})</span>
      </h3>
      {events.length === 0 ? (
        <p className="px-4 py-6 text-sm text-gray-400">No driver-behaviour violations detected in this clip.</p>
      ) : (
        <div className="flex flex-col">
          {events.map((entry, index) => (
            <LogEntry key={index} entry={entry} onSeek={onSeek} />
          ))}
        </div>
      )}
    </div>
  );
};
