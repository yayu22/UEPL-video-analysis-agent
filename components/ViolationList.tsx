
import React, { useMemo } from 'react';
import { VideoType, AnalysisEntry } from '../types';
import { IN_CABIN_VIOLATIONS, ROAD_SIDE_VIOLATIONS } from '../constants';
import { CheckCircleIcon, XCircleIcon } from './icons';

interface ViolationListProps {
  videoType: VideoType;
  analysisResult: AnalysisEntry[];
}

export const ViolationList: React.FC<ViolationListProps> = ({ videoType, analysisResult }) => {
  const violations = videoType === VideoType.InCabin ? IN_CABIN_VIOLATIONS : ROAD_SIDE_VIOLATIONS;
  
  const detectedViolations = useMemo(() => {
    return new Set(analysisResult.map(entry => entry.event));
  }, [analysisResult]);

  return (
    <div className="w-full bg-gray-800/50 backdrop-blur-sm p-6 rounded-2xl border border-gray-700 shadow-xl">
      <h3 className="text-xl font-bold text-indigo-300 mb-4 border-b border-gray-700 pb-2">
        Violation Checklist
      </h3>
      <ul className="space-y-3">
        {violations.map((violation) => {
          const isDetected = detectedViolations.has(violation);
          return (
            <li key={violation} className="flex items-center justify-between p-3 bg-gray-900/50 rounded-lg">
              <span className={`text-sm ${isDetected ? 'text-red-400' : 'text-gray-300'}`}>
                {violation}
              </span>
              {isDetected ? (
                <div className="flex items-center space-x-1 text-red-400">
                    <XCircleIcon className="w-5 h-5" />
                    <span className="text-xs font-semibold">DETECTED</span>
                </div>
              ) : (
                <div className="flex items-center space-x-1 text-green-400">
                    <CheckCircleIcon className="w-5 h-5" />
                    <span className="text-xs font-semibold">CLEAR</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
