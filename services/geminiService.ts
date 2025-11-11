import { GoogleGenAI, Type } from '@google/genai';
import { AnalysisEntry, EquipmentIssue, VideoType } from '../types';
import { 
  IN_CABIN_PROMPT, 
  ROAD_SIDE_PROMPT,
  EQUIPMENT_ANALYSIS_PROMPT
} from '../constants';

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

/**
 * Converts a File object to a GoogleGenAI.Part object for whole file upload.
 * @param file The file to convert.
 * @returns A promise that resolves to a Part object.
 */
async function fileToGenerativePart(file: File): Promise<{ inlineData: { data: string; mimeType: string; }; }> {
  const base64EncodedDataPromise = new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
        if (typeof reader.result === 'string') {
            resolve(reader.result.split(',')[1]);
        } else {
            reject(new Error("Failed to read file as data URL."));
        }
    };
    reader.onerror = (error) => reject(error);
    reader.readAsDataURL(file);
  });

  return {
    inlineData: {
      data: await base64EncodedDataPromise,
      mimeType: file.type,
    },
  };
}

const behaviorResponseSchema = {
  type: Type.ARRAY,
  items: {
    type: Type.OBJECT,
    properties: {
      frame: {
        type: Type.INTEGER,
        description: 'The approximate frame number where the event occurred within the video segment.',
      },
      timestamp: {
        type: Type.STRING,
        description: "The timestamp read directly from the video frame's text overlay (if available).",
      },
      event: {
        type: Type.STRING,
        description: 'The type of violation detected from the specified categories.',
      },
      confidence: {
        type: Type.NUMBER,
        description: 'The confidence score (from 0.0 to 1.0) of the detection.',
      },
      reason: {
        type: Type.STRING,
        description: 'A brief explanation for why this event was flagged.',
      },
    },
    required: ['frame', 'timestamp', 'event', 'confidence', 'reason'],
  },
};

const equipmentResponseSchema = {
  type: Type.ARRAY,
  items: {
      type: Type.OBJECT,
      properties: {
          issue: {
              type: Type.STRING,
              description: 'The type of equipment/video issue detected from the predefined list.',
          },
          reason: {
              type: Type.STRING,
              description: 'A brief explanation for why this issue was flagged.',
          },
      },
      required: ['issue', 'reason'],
  },
};


/**
 * Efficiently extracts frames from a video and sends them in batches for analysis.
 * This method is used for road-side analysis to optimize for speed and cost by parallelizing API calls.
 * @param file The video file.
 * @returns A promise that resolves to an array of analysis entries.
 */
async function analyzeRoadsideVideoByFrames(file: File): Promise<AnalysisEntry[]> {
  const videoUrl = URL.createObjectURL(file);
  const video = document.createElement('video');
  const canvas = document.createElement('canvas');
  video.muted = true;
  video.src = videoUrl;

  await new Promise<void>((resolve, reject) => {
    video.addEventListener('loadedmetadata', () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      resolve();
    }, { once: true });
    video.addEventListener('error', () => reject(new Error("Failed to load video metadata.")), { once: true });
  });

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error("Could not get canvas context.");
  }

  // This function uses a single, shared video element for efficient sequential seeking.
  const extractFrame = (time: number): Promise<string> => {
    return new Promise((resolve, reject) => {
      const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked);
        video.removeEventListener('error', onError);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', 0.8).split(',')[1]);
      };
      
      const onError = () => {
        video.removeEventListener('seeked', onSeeked);
        video.removeEventListener('error', onError);
        reject(new Error("Error seeking video to extract frame."));
      };

      video.addEventListener('seeked', onSeeked, { once: true });
      video.addEventListener('error', onError, { once: true });
      video.currentTime = time;
    });
  };

  const duration = video.duration;
  const CHUNK_DURATION_SECONDS = 5;
  const allFrameBatches: string[][] = [];

  // Step 1: Sequentially extract all frames and organize them into batches.
  console.log("Starting sequential frame extraction...");
  for (let chunkStart = 0; chunkStart < duration; chunkStart += CHUNK_DURATION_SECONDS) {
    const frameTimestamps: number[] = [];
    const chunkEnd = Math.min(chunkStart + CHUNK_DURATION_SECONDS, duration);

    // Collect timestamps for 2 frames per second
    for (let sec = Math.floor(chunkStart); sec < Math.floor(chunkEnd); sec++) {
      frameTimestamps.push(sec);
      frameTimestamps.push(sec + 0.5);
    }

    if (frameTimestamps.length > 0) {
      const frameDataBatch: string[] = [];
      // Extract frames sequentially for this batch.
      for (const time of frameTimestamps) {
        try {
          const frameData = await extractFrame(time);
          frameDataBatch.push(frameData);
        } catch (error) {
          console.warn(`Could not extract frame at time ${time}:`, error);
        }
      }
      if (frameDataBatch.length > 0) {
        allFrameBatches.push(frameDataBatch);
      }
    }
  }
  console.log(`Frame extraction complete. ${allFrameBatches.length} batches created.`);

  // Step 2: Create API call promises for each batch of frames.
  const analysisPromises = allFrameBatches.map(frameDataBatch => {
    const frameParts = frameDataBatch.map(data => ({
      inlineData: { data, mimeType: 'image/jpeg' }
    }));
    
    const textPart = { text: ROAD_SIDE_PROMPT };
    const contents = [{ parts: [textPart, ...frameParts] }];
    
    return ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: contents,
      config: {
        responseMimeType: "application/json",
        responseSchema: behaviorResponseSchema,
        temperature: 0.1,
        topP: 0.8,
        topK: 32,
        seed: 42,
      },
    });
  });

  // Step 3: Execute all API calls in parallel.
  console.log(`Executing ${analysisPromises.length} analysis batches in parallel...`);
  const responses = await Promise.all(analysisPromises);

  // Step 4: Process all responses and aggregate the results.
  const allAnalysisEntries: AnalysisEntry[] = [];
  for (const response of responses) {
    const finishReason = response.candidates?.[0]?.finishReason;
    if (finishReason && finishReason !== 'STOP') {
      console.error(`Road-side analysis stopped on a batch. Reason: ${finishReason}`);
      continue; // Skip this batch's result
    }

    const responseText = response.text?.trim();
    if (responseText) {
      try {
          const batchResult = JSON.parse(responseText) as AnalysisEntry[];
          allAnalysisEntries.push(...batchResult);
      } catch (e) {
          console.error("Failed to parse JSON response from batch:", responseText);
      }
    }
  }

  URL.revokeObjectURL(videoUrl);
  return allAnalysisEntries;
}


/**
 * Analyzes a video file for driving violations using the Gemini API.
 * Dispatches to either frame-based or full-video analysis based on video type.
 * @param file The video file to analyze.
 * @param type The type of video analysis to perform (in-cabin or road-side).
 * @returns A promise that resolves to an array of analysis entries.
 */
export const analyzeVideo = async (file: File, type: VideoType): Promise<AnalysisEntry[]> => {
  try {
    if (type === VideoType.RoadSide) {
      // Use the new, efficient frame-based method for road-side videos
      return await analyzeRoadsideVideoByFrames(file);
    } else {
      // Use the original full-video method for in-cabin to include audio analysis
      const prompt = IN_CABIN_PROMPT;
      const videoPart = await fileToGenerativePart(file);
      const textPart = { text: prompt };
      const contents = [{ parts: [textPart, videoPart] }];

      const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash',
        contents: contents,
        config: {
          responseMimeType: "application/json",
          responseSchema: behaviorResponseSchema,
          temperature: 0.1,
          topP: 0.8,
          topK: 32,
          seed: 42,
        },
      });

      const finishReason = response.candidates?.[0]?.finishReason;
      if (finishReason && finishReason !== 'STOP') {
        throw new Error(`Behavior analysis stopped. Reason: ${finishReason}`);
      }

      const responseText = response.text?.trim();
      if (!responseText) {
        throw new Error(`The AI model returned an empty behavior analysis. Finish reason: ${finishReason || 'Unknown'}`);
      }
      return JSON.parse(responseText) as AnalysisEntry[];
    }
  } catch (error) {
    console.error("Error in behavior analysis:", error);
    if (error instanceof Error) {
        throw new Error(`Behavior analysis failed: ${error.message}`);
    }
    throw new Error('An unknown error occurred during behavior analysis.');
  }
};

/**
 * Analyzes a video file for equipment and quality issues using the Gemini API.
 * This always uses the full video file to be able to check for audio issues.
 * @param file The video file to analyze.
 * @returns A promise that resolves to an array of equipment issue entries.
 */
export const analyzeEquipment = async (file: File): Promise<EquipmentIssue[]> => {
  try {
    const videoPart = await fileToGenerativePart(file);
    const textPart = { text: EQUIPMENT_ANALYSIS_PROMPT };
    const contents = [{ parts: [textPart, videoPart] }];

    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash-lite',
      contents: contents,
      config: {
        responseMimeType: "application/json",
        responseSchema: equipmentResponseSchema,
        temperature: 0.1,
        topP: 0.8,
        topK: 32,
        seed: 42,
      },
    });

    const finishReason = response.candidates?.[0]?.finishReason;
    if (finishReason && finishReason !== 'STOP') {
      throw new Error(`Equipment analysis stopped. Reason: ${finishReason}`);
    }
    
    const responseText = response.text?.trim();
    if (!responseText) {
      if(finishReason && finishReason !== 'STOP') {
         throw new Error(`The AI model returned an empty equipment analysis. Finish reason: ${finishReason}`);
      }
      return [];
    }

    return JSON.parse(responseText) as EquipmentIssue[];

  } catch (error) {
    console.error("Error in equipment analysis:", error);
    if (error instanceof Error) {
        throw new Error(`Equipment analysis failed: ${error.message}`);
    }
    throw new Error('An unknown error occurred during equipment analysis.');
  }
};