export enum VideoType {
  Cabin = 'cabin',   // in-cabin, driver-facing (with audio)
  Front = 'front',   // forward / road-facing
}

export type Severity = 'low' | 'medium' | 'high';

// One detected driver-behaviour event (matches the backend behaviour schema).
export interface BehaviourEvent {
  reason: string;
  category: string;
  severity: Severity;
  confidence: number;      // 0.0 - 1.0
  timestamp: string;       // overlay clock "HH:MM:SS" or "not visible"
  start_s: number;         // approx seconds from clip start (for seeking)
  end_s: number;
  speed_kmh?: number | null;
  camera?: string;
}

// One equipment / video-QA issue.
export interface EquipmentIssue {
  reason: string;
  issue: string;
  severity: Severity;
  confidence: number;
}

export interface CategoryStat {
  count: number;
  max_severity: Severity | null;
  points: number;
}

export interface DriverProfile {
  safety_score: number;    // 0-100, higher = safer
  grade: string;           // A-F
  grade_label: string;
  accident_detected?: boolean;
  risk_points: number;
  confirmed_event_count: number;
  review_event_count: number;
  per_category: Record<string, CategoryStat>;
  top_risks: (CategoryStat & { category: string })[];
  summary: string;
  review_items: BehaviourEvent[];
}

// Full response from POST /api/analyze
export interface AnalysisResponse {
  camera: string;
  view_ok: boolean;
  warnings: string[];
  events: BehaviourEvent[];
  equipment: EquipmentIssue[];
  profile: DriverProfile;
  filename?: string;
}
