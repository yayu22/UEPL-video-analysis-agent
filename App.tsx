import React, { useState, useMemo, useRef, useEffect } from 'react';
import { VideoUpload } from './components/VideoUpload';
import { VideoPlayer } from './components/VideoPlayer';
import { ViolationList } from './components/ViolationList';
import { AnalysisLog } from './components/AnalysisLog';
import { EquipmentChecklist } from './components/EquipmentChecklist';
import { DriverProfileCard } from './components/DriverProfileCard';
import { analyzeVideo } from './services/apiService';
import { VideoType, AnalysisResponse } from './types';

export default function App() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoType, setVideoType] = useState<VideoType | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [showResults, setShowResults] = useState<boolean>(false);

  const videoRef = useRef<HTMLVideoElement>(null);

  const videoUrl = useMemo(() => (videoFile ? URL.createObjectURL(videoFile) : ''), [videoFile]);

  // Revoke the previous object URL when the file changes / unmounts (no leaks).
  useEffect(() => {
    return () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    };
  }, [videoUrl]);

  const handleSeek = (seconds: number) => {
    const v = videoRef.current;
    if (v && Number.isFinite(seconds)) {
      v.currentTime = seconds;
      v.play?.().catch(() => { /* autoplay may be blocked; ignore */ });
    }
  };

  const handleAnalyze = async (file: File, type: VideoType) => {
    setIsLoading(true);
    setError('');
    setResult(null);
    setVideoFile(file);
    setVideoType(type);
    setShowResults(true);

    try {
      const res = await analyzeVideo(file, type);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred during analysis.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setVideoFile(null);
    setVideoType(null);
    setResult(null);
    setError('');
    setShowResults(false);
  };

  const cameraLabel = videoType === VideoType.Cabin ? 'Cabin Camera' : 'Front Camera';

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 font-sans p-4 sm:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto">
        <header className="text-center mb-10">
          <h1 className="text-4xl sm:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            Driver Profiling & Equipment Analysis
          </h1>
          <p className="mt-2 text-lg text-gray-400">
            Upload a cabin or front dashcam clip to profile driving behaviour and check equipment health.
          </p>
        </header>

        {!showResults ? (
          <VideoUpload onAnalyze={handleAnalyze} isLoading={isLoading} />
        ) : (
          <div>
            {/* Camera-view mismatch / other backend warnings */}
            {result?.warnings?.map((w, i) => (
              <div key={i} className="mb-6 p-4 bg-amber-900/40 border border-amber-700 rounded-lg text-amber-200 text-sm">
                <strong>⚠ Warning:</strong> {w}
              </div>
            ))}

            {result?.profile && !isLoading && <DriverProfileCard profile={result.profile} />}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2">
                <div className="mb-2 text-sm text-gray-400">
                  {cameraLabel}{result?.filename ? ` · ${result.filename}` : ''}
                </div>
                <VideoPlayer ref={videoRef} videoUrl={videoUrl} />
                <AnalysisLog events={result?.events ?? []} isLoading={isLoading} onSeek={handleSeek} />
              </div>
              <div className="lg:col-span-1 space-y-8">
                {videoType && (
                  <ViolationList videoType={videoType} events={result?.events ?? []} />
                )}
                <EquipmentChecklist equipmentIssues={result?.equipment ?? []} />
              </div>
            </div>

            {error && (
              <div className="mt-8 text-center p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-300">
                <p><strong>Error:</strong> {error}</p>
              </div>
            )}

            <div className="text-center mt-8">
              <button
                onClick={handleReset}
                className="bg-gray-700 text-white font-bold py-2 px-6 rounded-lg hover:bg-gray-600 transition-colors duration-300"
              >
                Analyze Another Video
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
