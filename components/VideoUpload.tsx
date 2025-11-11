
import React, { useState, useCallback } from 'react';
import { VideoType } from '../types';
import { UploadIcon, SpinnerIcon } from './icons';

interface VideoUploadProps {
  onAnalyze: (file: File, type: VideoType) => void;
  isLoading: boolean;
}

const VideoTypeSelector: React.FC<{ selectedType: VideoType | null, onSelect: (type: VideoType) => void }> = ({ selectedType, onSelect }) => (
    <div className="flex justify-center space-x-4 my-4">
        {(Object.values(VideoType)).map((type) => (
            <button
                key={type}
                onClick={() => onSelect(type)}
                className={`px-6 py-3 rounded-lg text-sm font-semibold transition-all duration-200 ease-in-out transform hover:scale-105 ${
                    selectedType === type
                        ? 'bg-indigo-600 text-white shadow-lg'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
            >
                {type === VideoType.InCabin ? 'In-Cabin Analysis' : 'Road-Side Analysis'}
            </button>
        ))}
    </div>
);

export const VideoUpload: React.FC<VideoUploadProps> = ({ onAnalyze, isLoading }) => {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoType, setVideoType] = useState<VideoType | null>(null);
  const [error, setError] = useState<string>('');

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (file.type.startsWith('video/')) {
        setVideoFile(file);
        setError('');
      } else {
        setError('Please upload a valid video file.');
        setVideoFile(null);
      }
    }
  };

  const handleSubmit = () => {
    if (videoFile && videoType) {
      onAnalyze(videoFile, videoType);
    } else {
      setError('Please select a video type and upload a video file.');
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto p-8 bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-gray-700 shadow-2xl text-center">
        <h2 className="text-2xl font-bold text-indigo-300 mb-2">Select Video Type</h2>
        <p className="text-gray-400 mb-6">Choose the context for a more accurate behavior analysis.</p>
        
        <VideoTypeSelector selectedType={videoType} onSelect={setVideoType} />

        <div className="mt-8">
            <label htmlFor="video-upload" className="cursor-pointer group">
                <div className="flex flex-col items-center justify-center h-40 border-2 border-dashed border-gray-600 rounded-lg group-hover:border-indigo-500 transition-colors duration-200 bg-gray-900/50">
                    <UploadIcon className="w-10 h-10 text-gray-500 group-hover:text-indigo-400 mb-2" />
                    <p className="text-gray-400 group-hover:text-indigo-300">
                        {videoFile ? videoFile.name : 'Click to upload video'}
                    </p>
                    <p className="text-xs text-gray-500">MP4, WEBM, MOV</p>
                </div>
            </label>
            <input id="video-upload" type="file" accept="video/*" className="hidden" onChange={handleFileChange} />
        </div>

      {error && <p className="text-red-400 mt-4 text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={!videoFile || !videoType || isLoading}
        className="mt-8 w-full flex items-center justify-center bg-indigo-600 text-white font-bold py-3 px-6 rounded-lg hover:bg-indigo-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-all duration-300 transform hover:scale-105 shadow-lg"
      >
        {isLoading ? (
            <>
                <SpinnerIcon className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" />
                Analyzing...
            </>
        ) : (
            'Start Analysis'
        )}
      </button>
    </div>
  );
};
