import React from 'react';
import { DriverProfile } from '../types';

const gradeColor = (grade: string): string => {
  switch (grade) {
    case 'A': return 'from-green-400 to-emerald-500';
    case 'B': return 'from-lime-400 to-green-500';
    case 'C': return 'from-amber-400 to-yellow-500';
    case 'D': return 'from-orange-400 to-amber-500';
    default:  return 'from-red-500 to-rose-600';
  }
};

const sevBadge: Record<string, string> = {
  high: 'bg-red-500/20 text-red-300 border-red-600',
  medium: 'bg-amber-500/20 text-amber-300 border-amber-600',
  low: 'bg-yellow-500/20 text-yellow-200 border-yellow-600',
};

export const DriverProfileCard: React.FC<{ profile: DriverProfile }> = ({ profile }) => {
  if (!profile) return null;
  return (
    <div className="w-full bg-gray-800/50 backdrop-blur-sm p-6 rounded-2xl border border-gray-700 shadow-xl mb-8">
      {profile.accident_detected && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-600 bg-red-600/20 px-4 py-3 text-red-200 font-semibold">
          <span className="text-lg">⚠</span>
          Accident / collision detected — driver rating forced to F. Immediate review required.
        </div>
      )}
      <div className="flex items-center gap-6">
        {/* Grade dial */}
        <div className={`flex-shrink-0 h-24 w-24 rounded-2xl bg-gradient-to-br ${gradeColor(profile.grade)} flex flex-col items-center justify-center shadow-lg`}>
          <span className="text-4xl font-black text-white leading-none">{profile.grade}</span>
          <span className="text-[10px] uppercase tracking-wider text-white/80 mt-1">{profile.grade_label}</span>
        </div>

        <div className="flex-grow">
          <div className="flex items-baseline gap-2">
            <h3 className="text-xl font-bold text-indigo-300">Driver Safety Profile</h3>
            <span className="text-sm text-gray-400">— score {profile.safety_score}/100</span>
          </div>
          {/* Score bar */}
          <div className="mt-2 h-2.5 w-full bg-gray-900 rounded-full overflow-hidden">
            <div
              className={`h-full bg-gradient-to-r ${gradeColor(profile.grade)}`}
              style={{ width: `${Math.max(0, Math.min(100, profile.safety_score))}%` }}
            />
          </div>
          <p className="mt-3 text-sm text-gray-300">{profile.summary}</p>
          <div className="mt-2 text-xs text-gray-500">
            {profile.confirmed_event_count} confirmed event(s)
            {profile.review_event_count > 0 && ` · ${profile.review_event_count} for review`}
            {` · ${profile.risk_points} risk points`}
          </div>
        </div>
      </div>

      {profile.top_risks?.length > 0 && (
        <div className="mt-5">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Top risks</h4>
          <div className="flex flex-wrap gap-2">
            {profile.top_risks.map((r) => (
              <span
                key={r.category}
                className={`text-xs px-2.5 py-1 rounded-full border ${sevBadge[r.max_severity ?? 'low']}`}
              >
                {r.category} · {r.count}× {r.max_severity && `(${r.max_severity})`}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
