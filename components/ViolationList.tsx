import React, { useMemo } from 'react';
import { VideoType, BehaviourEvent, Severity } from '../types';
import { categoriesFor } from '../constants';
import { CheckCircleIcon, XCircleIcon } from './icons';

interface ViolationListProps {
  videoType: VideoType;
  events: BehaviourEvent[];
}

const sevText: Record<Severity, string> = {
  high: 'text-red-400',
  medium: 'text-amber-400',
  low: 'text-yellow-300',
};

export const ViolationList: React.FC<ViolationListProps> = ({ videoType, events }) => {
  const categories = categoriesFor(videoType);

  // category -> worst severity + count
  const detected = useMemo(() => {
    const map = new Map<string, { severity: Severity; count: number }>();
    const order: Record<Severity, number> = { low: 0, medium: 1, high: 2 };
    for (const e of events) {
      const cur = map.get(e.category);
      if (!cur) map.set(e.category, { severity: e.severity, count: 1 });
      else map.set(e.category, {
        severity: order[e.severity] > order[cur.severity] ? e.severity : cur.severity,
        count: cur.count + 1,
      });
    }
    return map;
  }, [events]);

  return (
    <div className="w-full bg-gray-800/50 backdrop-blur-sm p-6 rounded-2xl border border-gray-700 shadow-xl">
      <h3 className="text-xl font-bold text-indigo-300 mb-4 border-b border-gray-700 pb-2">
        Violation Checklist
      </h3>
      <ul className="space-y-3">
        {categories.map((category) => {
          const hit = detected.get(category);
          return (
            <li key={category} className="flex items-center justify-between p-3 bg-gray-900/50 rounded-lg">
              <span className={`text-sm ${hit ? sevText[hit.severity] : 'text-gray-300'}`}>
                {category}
              </span>
              {hit ? (
                <div className={`flex items-center space-x-1 ${sevText[hit.severity]}`}>
                  <XCircleIcon className="w-5 h-5" />
                  <span className="text-xs font-semibold uppercase">
                    {hit.severity}{hit.count > 1 ? ` ×${hit.count}` : ''}
                  </span>
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
