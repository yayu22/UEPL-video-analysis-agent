import React, { forwardRef } from 'react';

interface VideoPlayerProps {
  videoUrl: string;
}

// forwardRef so the parent can seek the video to a violation's timestamp.
export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  ({ videoUrl }, ref) => {
    return (
      <div className="w-full bg-black rounded-lg overflow-hidden border border-gray-700 shadow-lg">
        <video
          ref={ref}
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
  }
);

VideoPlayer.displayName = 'VideoPlayer';
