export enum VideoType {
  InCabin = 'in-cabin',
  RoadSide = 'road-side',
}

export interface AnalysisEntry {
  frame: number;
  timestamp: string;
  event: string;
  confidence: number;
  reason: string;
}

export interface EquipmentIssue {
  issue: string;
  reason: string;
}