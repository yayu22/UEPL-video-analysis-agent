import React, { useState, useMemo } from 'react';
import { VideoUpload } from './components/VideoUpload';
import { VideoPlayer } from './components/VideoPlayer';
import { ViolationList } from './components/ViolationList';
import { AnalysisLog } from './components/AnalysisLog';
import { EquipmentChecklist } from './components/EquipmentChecklist';
import { analyzeVideo, analyzeEquipment } from './services/geminiService';
import { VideoType, AnalysisEntry, EquipmentIssue } from './types';

export default function App() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoType, setVideoType] = useState<VideoType | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisEntry[]>([]);
  const [equipmentIssues, setEquipmentIssues] = useState<EquipmentIssue[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [showResults, setShowResults] = useState<boolean>(false);

  const videoUrl = useMemo(() => {
    if (videoFile) {
      return URL.createObjectURL(videoFile);
    }
    return '';
  }, [videoFile]);

  const handleAnalyze = async (file: File, type: VideoType) => {
    setIsLoading(true);
    setError('');
    setAnalysisResult([]);
    setEquipmentIssues([]);
    setVideoFile(file);
    setVideoType(type);
    setShowResults(true);

    try {
      // Run both analyses in parallel for efficiency
      const [behaviorResult, equipmentResult] = await Promise.all([
        analyzeVideo(file, type),
        analyzeEquipment(file)
      ]);
      setAnalysisResult(behaviorResult);
      setEquipmentIssues(equipmentResult);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred during analysis.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setVideoFile(null);
    setVideoType(null);
    setAnalysisResult([]);
    setEquipmentIssues([]);
    setError('');
    setShowResults(false);
    if(videoUrl) {
      URL.revokeObjectURL(videoUrl);
    }
  };


  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 font-sans p-4 sm:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto">
        <header className="text-center mb-10">
          <h1 className="text-4xl sm:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            Driving Behavior Analysis Agent
          </h1>
          <p className="mt-2 text-lg text-gray-400">
            Upload a video to evaluate driving behavior and equipment status using Gemini.
          </p>
        </header>

        {!showResults ? (
          <VideoUpload onAnalyze={handleAnalyze} isLoading={isLoading} />
        ) : (
          <div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2">
                <VideoPlayer videoUrl={videoUrl} />
                <AnalysisLog analysisResult={analysisResult} isLoading={isLoading} />
              </div>
              <div className="lg:col-span-1 space-y-8">
                {videoType && (
                  <ViolationList videoType={videoType} analysisResult={analysisResult} />
                )}
                <EquipmentChecklist equipmentIssues={equipmentIssues} />
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
