
import React from 'react';

interface VideoPlayerProps {
  videoUrl: string;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({ videoUrl }) => {
  return (
    <div className="w-full bg-black rounded-lg overflow-hidden border border-gray-700 shadow-lg">
      <video
        key={videoUrl}
        className="w-full aspect-video"
        controls
        autoPlay
        muted
      >
        <source src={videoUrl} />
        Your browser does not support the video tag.
      </video>
    </div>
  );
};
