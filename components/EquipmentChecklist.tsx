import React, { useMemo } from 'react';
import { EquipmentIssue, Severity } from '../types';
import { EQUIPMENT_CHECKLIST_ITEMS } from '../constants';
import { CheckCircleIcon, XCircleIcon } from './icons';

interface EquipmentChecklistProps {
  equipmentIssues: EquipmentIssue[];
}

const sevText: Record<Severity, string> = {
  high: 'text-red-400',
  medium: 'text-amber-400',
  low: 'text-yellow-300',
};

export const EquipmentChecklist: React.FC<EquipmentChecklistProps> = ({ equipmentIssues }) => {
  const detected = useMemo(
    () => new Map(equipmentIssues.map((i) => [i.issue, i])),
    [equipmentIssues]
  );

  return (
    <div className="w-full bg-gray-800/50 backdrop-blur-sm p-6 rounded-2xl border border-gray-700 shadow-xl">
      <h3 className="text-xl font-bold text-indigo-300 mb-4 border-b border-gray-700 pb-2">
        Equipment Checklist
      </h3>
      <div className="space-y-4">
        {Object.entries(EQUIPMENT_CHECKLIST_ITEMS).map(([category, items]) => (
          <div key={category}>
            <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">{category}</h4>
            <ul className="space-y-3">
              {items.map((item) => {
                const hit = detected.get(item);
                return (
                  <li key={item} className="p-3 bg-gray-900/50 rounded-lg">
                    <div className="flex items-center justify-between">
                      <span className={`text-sm ${hit ? sevText[hit.severity] : 'text-gray-300'}`}>
                        {item}
                      </span>
                      {hit ? (
                        <div className={`flex items-center space-x-1 flex-shrink-0 ${sevText[hit.severity]}`}>
                          <XCircleIcon className="w-5 h-5" />
                          <span className="text-xs font-semibold uppercase">{hit.severity}</span>
                        </div>
                      ) : (
                        <div className="flex items-center space-x-1 text-green-400 flex-shrink-0">
                          <CheckCircleIcon className="w-5 h-5" />
                          <span className="text-xs font-semibold">CLEAR</span>
                        </div>
                      )}
                    </div>
                    {hit?.reason && (
                      <p className="mt-2 text-xs text-gray-400 border-l-2 border-red-500 pl-2">
                        <span className="font-semibold">Reason:</span> {hit.reason}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
};
