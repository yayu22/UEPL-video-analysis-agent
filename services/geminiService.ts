import { GoogleGenAI, Type } from '@google/genai';
import { AnalysisEntry, EquipmentIssue, VideoType } from '../types';
import { 
  IN_CABIN_PROMPT, 
  ROAD_SIDE_PROMPT,
  EQUIPMENT_ANALYSIS_PROMPT
} from '../constants';

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

/**
 * Converts a File object to a GoogleGenAI.Part object.
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
        description: 'The approximate frame number where the event occurred.',
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
 * Analyzes a video file for driving violations using the Gemini API.
 * @param file The video file to analyze.
 * @param type The type of video analysis to perform (in-cabin or road-side).
 * @returns A promise that resolves to an array of analysis entries.
 */
export const analyzeVideo = async (file: File, type: VideoType): Promise<AnalysisEntry[]> => {
  const prompt = type === VideoType.InCabin ? IN_CABIN_PROMPT : ROAD_SIDE_PROMPT;

  try {
    const videoPart = await fileToGenerativePart(file);
    const textPart = { text: prompt };

    const contents = [{ parts: [textPart, videoPart] }];

    const response = await ai.models.generateContent({
      model: 'gemini-2.5-pro',
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
 * @param file The video file to analyze.
 * @returns A promise that resolves to an array of equipment issue entries.
 */
export const analyzeEquipment = async (file: File): Promise<EquipmentIssue[]> => {
  try {
    const videoPart = await fileToGenerativePart(file);
    const textPart = { text: EQUIPMENT_ANALYSIS_PROMPT };
    const contents = [{ parts: [textPart, videoPart] }];

    const response = await ai.models.generateContent({
      model: 'gemini-2.5-pro',
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
      // It's common for there to be no equipment issues, so an empty response is valid.
      // We only throw if the finish reason indicates an actual problem.
      if(finishReason && finishReason !== 'STOP') {
         throw new Error(`The AI model returned an empty equipment analysis. Finish reason: ${finishReason}`);
      }
      return []; // Return empty array if response is empty but finish reason is STOP.
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