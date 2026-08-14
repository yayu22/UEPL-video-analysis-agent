import { VideoType } from './types';

// Backend base URL. Override at build time with VITE_API_BASE.
export const API_BASE =
  (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000';

// --------------------------------------------------------------------------- //
// Taxonomies — MUST match backend/config.py. Used to render the checklists so a
// category is shown even when it wasn't detected (as "CLEAR").
// The backend also exposes these at GET /api/taxonomy if you prefer to fetch them.
// --------------------------------------------------------------------------- //
export const CABIN_CATEGORIES = [
  'Unauthorized Passenger',
  'Distracted Driving',
  'Driver No Seatbelt',
  'Driver Fatigue',
  'Casual Driving',
  'Smoking',
  'Road Rage',
  'FOD Violation',
  'Loose Items',
];

export const FRONT_CATEGORIES = [
  'Lane Discipline',
  'Speed Violation',
  'Improper Overtaking',
  'Improper Turn',
  'Tailgating',
  'Harsh Driving',
];

export const EQUIPMENT_CHECKLIST_ITEMS: Record<string, string[]> = {
  Camera: [
    'Camera Not Working',
    'Overlay Data Stuck Or Zero',
    'Incorrect Camera Angle',
    'Audio Missing',
    'Video Blurred',
    'View Obstructed',
    'Poor Night Vision',
  ],
  Video: [
    'Video Buffering',
    'Video Jump Or Missing Segment',
    'Audio Video Out Of Sync',
  ],
};

export const categoriesFor = (type: VideoType): string[] =>
  type === VideoType.Cabin ? CABIN_CATEGORIES : FRONT_CATEGORIES;

export const SEVERITY_COLORS: Record<string, string> = {
  high: 'text-red-400',
  medium: 'text-amber-400',
  low: 'text-yellow-300',
};
