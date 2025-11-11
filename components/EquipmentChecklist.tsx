import React, { useMemo } from 'react';
import { EquipmentIssue } from '../types';
import { EQUIPMENT_CHECKLIST_ITEMS } from '../constants';
import { CheckCircleIcon, XCircleIcon } from './icons';

interface EquipmentChecklistProps {
  equipmentIssues: EquipmentIssue[];
}

export const EquipmentChecklist: React.FC<EquipmentChecklistProps> = ({ equipmentIssues }) => {
  const detectedIssues = useMemo(() => {
    return new Map(equipmentIssues.map(issue => [issue.issue, issue.reason]));
  }, [equipmentIssues]);

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
                const isDetected = detectedIssues.has(item);
                const reason = detectedIssues.get(item);
                return (
                  <li key={item} className="p-3 bg-gray-900/50 rounded-lg">
                    <div className="flex items-center justify-between">
                       <span className={`text-sm ${isDetected ? 'text-red-400' : 'text-gray-300'}`}>
                          {item}
                       </span>
                       {isDetected ? (
                         <div className="flex items-center space-x-1 text-red-400 flex-shrink-0">
                             <XCircleIcon className="w-5 h-5" />
                             <span className="text-xs font-semibold">DETECTED</span>
                         </div>
                       ) : (
                         <div className="flex items-center space-x-1 text-green-400 flex-shrink-0">
                             <CheckCircleIcon className="w-5 h-5" />
                             <span className="text-xs font-semibold">CLEAR</span>
                         </div>
                       )}
                    </div>
                    {isDetected && reason && (
                        <p className="mt-2 text-xs text-gray-400 border-l-2 border-red-500 pl-2">
                            <span className="font-semibold">Reason:</span> {reason}
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
