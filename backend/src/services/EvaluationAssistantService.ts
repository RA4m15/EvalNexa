import { GoogleGenerativeAI } from '@google/generative-ai';
import { z } from 'zod';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { AnswerPage } from '../models/AnswerPage';
import { Question } from '../models/Question';
import { Exam } from '../models/Exam';

// =============================================================================
// TYPES & SCHEMAS
// =============================================================================

export interface EvaluationAssistantCriteriaSuggestion {
  name: string;
  maxMarks: number;
  awardedMarks: number;
  evidence: string;
}

export interface EvaluationAssistantResult {
  suggestedMarks: number;
  minMarks: number;
  maxMarks: number;
  confidence: number;
  needsHumanReview: boolean;
  criteria: EvaluationAssistantCriteriaSuggestion[];
  missingConcepts: string[];
  reasoningSummary: string;
}

export interface EvaluationAssistantInput {
  question: string;
  maximumMarks: number;
  rubric: Array<{
    criterion: string;
    marks: number;
  }>;
  referenceAnswer?: string;
  keyConcepts?: string[];
  gradingNotes?: string;
  studentAnswerImage?: string | Buffer;
  studentAnswerImageMimeType?: string;
  ocrText?: string;
  ocrConfidence?: number | null;
  language?: string;
}

export const evaluationAssistantResultSchema = z.object({
  suggestedMarks: z.number().min(0),
  minMarks: z.number().min(0),
  maxMarks: z.number().min(0),
  confidence: z.number().min(0).max(1),
  needsHumanReview: z.boolean(),
  criteria: z.array(
    z.object({
      name: z.string(),
      maxMarks: z.number().min(0),
      awardedMarks: z.number().min(0),
      evidence: z.string().default(''),
    })
  ),
  missingConcepts: z.array(z.string()).default([]),
  reasoningSummary: z.string().default(''),
});

// =============================================================================
// LOGGING HELPER (Redacts sensitive PII & student content)
// =============================================================================

function logAssistantEvent(
  level: 'info' | 'warn' | 'error',
  message: string,
  meta?: Record<string, unknown>
): void {
  const timestamp = new Date().toISOString();
  const logPayload = {
    timestamp,
    service: 'EvaluationAssistantService',
    level,
    message,
    ...meta,
  };

  if (level === 'error') {
    console.error(JSON.stringify(logPayload));
  } else if (level === 'warn') {
    console.warn(JSON.stringify(logPayload));
  } else {
    console.log(JSON.stringify(logPayload));
  }
}

// =============================================================================
// IMAGE RESOLVER HELPER
// =============================================================================

async function resolveImagePart(
  imageInput: string | Buffer,
  fallbackMimeType = 'image/jpeg'
): Promise<{ inlineData: { data: string; mimeType: string } } | null> {
  try {
    if (Buffer.isBuffer(imageInput)) {
      return {
        inlineData: {
          data: imageInput.toString('base64'),
          mimeType: fallbackMimeType,
        },
      };
    }

    if (typeof imageInput === 'string') {
      // 1. Data URL
      if (imageInput.startsWith('data:')) {
        const matches = imageInput.match(/^data:([a-zA-Z0-9]+\/[a-zA-Z0-9-.+]+);base64,(.+)$/);
        if (matches && matches.length === 3) {
          return {
            inlineData: {
              mimeType: matches[1],
              data: matches[2],
            },
          };
        }
      }

      // 2. HTTP/HTTPS URL
      if (imageInput.startsWith('http://') || imageInput.startsWith('https://')) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);
        try {
          const res = await fetch(imageInput, { signal: controller.signal });
          clearTimeout(timeoutId);
          if (!res.ok) {
            throw new Error(`Failed to fetch image: HTTP ${res.status}`);
          }
          const arrayBuffer = await res.arrayBuffer();
          const buffer = Buffer.from(arrayBuffer);
          const contentType = res.headers.get('content-type') || fallbackMimeType;
          return {
            inlineData: {
              data: buffer.toString('base64'),
              mimeType: contentType.split(';')[0].trim(),
            },
          };
        } catch (fetchErr: any) {
          clearTimeout(timeoutId);
          logAssistantEvent('warn', 'Failed to fetch image URL for assistant analysis', {
            error: fetchErr.message,
          });
          return null;
        }
      }

      // 3. Raw Base64 string
      return {
        inlineData: {
          data: imageInput,
          mimeType: fallbackMimeType,
        },
      };
    }

    return null;
  } catch (err: any) {
    logAssistantEvent('warn', 'Exception in resolveImagePart', { error: err.message });
    return null;
  }
}

// =============================================================================
// PROMPT BUILDER
// =============================================================================

function buildEvaluationPrompt(input: EvaluationAssistantInput): string {
  const rubricText =
    input.rubric.length > 0
      ? input.rubric
          .map((r, i) => `  ${i + 1}. [${r.criterion}]: Maximum ${r.marks} marks`)
          .join('\n')
      : `  1. [Overall Correctness and Completeness]: Maximum ${input.maximumMarks} marks`;

  return `You are an academic evaluation copilot assisting an accredited human examiner.
Your task is to analyze the student's response against the rubric and provide an initial scoring suggestion and evidence summary.
THE HUMAN EXAMINER MAKES THE FINAL DECISION.

=========================================
EXAMINATION SPECIFICATIONS
=========================================
Question:
${input.question}

Maximum Marks:
${input.maximumMarks}

Official Rubric:
${rubricText}

${input.referenceAnswer ? `Reference Model Answer:\n${input.referenceAnswer}\n` : ''}
${input.keyConcepts && input.keyConcepts.length > 0 ? `Key Concepts Required:\n${input.keyConcepts.map((c) => `- ${c}`).join('\n')}\n` : ''}
${input.gradingNotes ? `Grading Notes & Special Instructions:\n${input.gradingNotes}\n` : ''}
${input.language ? `Evaluation Language: ${input.language}\n` : ''}

=========================================
STUDENT RESPONSE
=========================================
${input.ocrText ? `Transcribed Student Answer (OCR):\n${input.ocrText}\n` : '(No OCR transcription available; inspect the attached script image)'}
${input.ocrConfidence !== undefined && input.ocrConfidence !== null ? `OCR Recognition Confidence: ${Math.round(input.ocrConfidence * 100)}%\n` : ''}

=========================================
MANDATORY EVALUATION RULES
=========================================
1. Evaluate the student's answer strictly against the rubric criteria.
2. Do NOT require exact wording. Accept semantically correct and conceptually equivalent explanations.
3. Consider paragraphs, bullet points, mathematical steps, formulas, and diagrams where present.
4. Provide direct, verifiable evidence (quotations or description of work) from the student response for each criterion.
5. Award partial credit when justified by the student's understanding and rubric rules.
6. Do NOT invent or assume content not present in the answer.
7. CRITICAL LIMIT: suggestedMarks MUST be >= 0 and <= ${input.maximumMarks}.
8. CRITICAL LIMIT: Each criterion awardedMarks MUST be >= 0 and <= criterion maxMarks.
9. Mark Range: minMarks <= suggestedMarks <= maxMarks, and maxMarks <= ${input.maximumMarks}.
10. Identify any ambiguity or uncertainty. Recommend human review (needsHumanReview = true) if confidence is low (< 0.75), handwriting is illegible, or answer is borderline.
11. Return a JSON object with this exact shape:
{
  "suggestedMarks": number,
  "minMarks": number,
  "maxMarks": number,
  "confidence": number,
  "needsHumanReview": boolean,
  "criteria": [
    {
      "name": "Criterion name",
      "maxMarks": number,
      "awardedMarks": number,
      "evidence": "Quoted evidence or description from student script"
    }
  ],
  "missingConcepts": ["concept1", ...],
  "reasoningSummary": "Brief explanation of marks awarded and deductions"
}`;
}

// =============================================================================
// VALIDATION & CONSTRAINT ENFORCEMENT
// =============================================================================

export function validateAndEnforceAssistantConstraints(
  raw: unknown,
  input: EvaluationAssistantInput
): EvaluationAssistantResult {
  const result = evaluationAssistantResultSchema.parse(raw);

  // 1. suggestedMarks bounds
  if (result.suggestedMarks < 0 || result.suggestedMarks > input.maximumMarks) {
    throw new Error(
      `AI suggestedMarks (${result.suggestedMarks}) out of bounds [0, ${input.maximumMarks}]`
    );
  }

  // 2. minMarks <= suggestedMarks
  if (result.minMarks > result.suggestedMarks) {
    throw new Error(
      `AI minMarks (${result.minMarks}) cannot exceed suggestedMarks (${result.suggestedMarks})`
    );
  }

  // 3. suggestedMarks <= maxMarks
  if (result.suggestedMarks > result.maxMarks) {
    throw new Error(
      `AI suggestedMarks (${result.suggestedMarks}) cannot exceed maxMarks (${result.maxMarks})`
    );
  }

  // 4. maxMarks <= question maximum
  if (result.maxMarks > input.maximumMarks) {
    throw new Error(
      `AI maxMarks (${result.maxMarks}) cannot exceed question maximum (${input.maximumMarks})`
    );
  }

  // 5. criteria marks never exceed rubric limits
  for (const crit of result.criteria) {
    if (crit.awardedMarks > crit.maxMarks) {
      throw new Error(
        `Criterion '${crit.name}' awarded marks (${crit.awardedMarks}) exceeds criterion maximum (${crit.maxMarks})`
      );
    }
  }

  // 6. confidence is between 0 and 1 (guaranteed by zod schema)

  return result;
}

// =============================================================================
// FALLBACK RESULT GENERATOR
// =============================================================================

function createFallbackResult(
  input: EvaluationAssistantInput,
  reason: string,
  evidenceMessage: string
): EvaluationAssistantResult {
  const criteriaList =
    input.rubric && input.rubric.length > 0
      ? input.rubric.map((r) => ({
          name: r.criterion,
          maxMarks: r.marks,
          awardedMarks: 0,
          evidence: evidenceMessage,
        }))
      : [
          {
            name: 'Overall Evaluation',
            maxMarks: input.maximumMarks,
            awardedMarks: 0,
            evidence: evidenceMessage,
          },
        ];

  return {
    suggestedMarks: 0,
    minMarks: 0,
    maxMarks: input.maximumMarks,
    confidence: 0,
    needsHumanReview: true,
    criteria: criteriaList,
    missingConcepts: input.keyConcepts || [],
    reasoningSummary: reason,
  };
}

// =============================================================================
// MAIN SERVICE IMPLEMENTATION
// =============================================================================

export class EvaluationAssistantService {
  /**
   * Evaluates a student's answer using Gemini Multimodal Model.
   * Never blocks manual examiner marking.
   */
  public static async evaluateStudentAnswer(
    input: EvaluationAssistantInput
  ): Promise<EvaluationAssistantResult> {
    const startTime = Date.now();

    // 1. Verify input existence and limits
    if (!input.question || input.maximumMarks <= 0) {
      logAssistantEvent('warn', 'Invalid input specifications provided to assistant');
      return createFallbackResult(
        input,
        'Invalid question specification. Examiner review required.',
        'Question or maximum marks missing.'
      );
    }

    // 2. Rule 7: If OCR quality is poor and answer image is unavailable, do not invent evaluation
    const hasImage = Boolean(input.studentAnswerImage);
    const hasOcr = Boolean(input.ocrText && input.ocrText.trim().length > 0);

    if (!hasImage && !hasOcr) {
      logAssistantEvent('info', 'No answer image or OCR text available for evaluation', {
        maximumMarks: input.maximumMarks,
      });
      return createFallbackResult(
        input,
        'No student script image or OCR transcription available. Human examiner review is required.',
        'Neither script image nor transcribed text was provided.'
      );
    }

    if (
      !hasImage &&
      input.ocrConfidence !== undefined &&
      input.ocrConfidence !== null &&
      input.ocrConfidence < 0.35
    ) {
      logAssistantEvent('info', 'OCR confidence too low and script image unavailable', {
        ocrConfidence: input.ocrConfidence,
      });
      return createFallbackResult(
        input,
        `OCR recognition quality is below acceptable threshold (${Math.round(input.ocrConfidence * 100)}%) and script image is unavailable. Examiner inspection required.`,
        'Low OCR transcription confidence.'
      );
    }

    // 3. Check GEMINI_API_KEY
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey || apiKey.trim() === '') {
      logAssistantEvent('warn', 'GEMINI_API_KEY not configured. Falling back to human review.');
      return createFallbackResult(
        input,
        'AI evaluation assistant is unconfigured (GEMINI_API_KEY missing). Proceed with manual examiner evaluation.',
        'AI copilot service unconfigured.'
      );
    }

    // 4. Execute AI Evaluation
    try {
      const genAI = new GoogleGenerativeAI(apiKey);
      const modelName = process.env.GEMINI_MODEL || 'gemini-1.5-flash';
      const model = genAI.getGenerativeModel({
        model: modelName,
        generationConfig: {
          responseMimeType: 'application/json',
          temperature: 0.1, // Low temperature for deterministic grading
        },
      });

      const prompt = buildEvaluationPrompt(input);
      const contents: Array<string | { inlineData: { data: string; mimeType: string } }> = [
        prompt,
      ];

      // Attach image if available
      if (input.studentAnswerImage) {
        const imagePart = await resolveImagePart(
          input.studentAnswerImage,
          input.studentAnswerImageMimeType
        );
        if (imagePart) {
          contents.push(imagePart);
        }
      }

      const response = await model.generateContent(contents);
      const responseText = response.response.text();

      // Parse JSON response
      let parsedRaw: unknown;
      try {
        parsedRaw = JSON.parse(responseText);
      } catch (jsonErr: any) {
        // Strip code fences if present
        const cleaned = responseText
          .replace(/```(?:json)?/gi, '')
          .replace(/```/g, '')
          .trim();
        parsedRaw = JSON.parse(cleaned);
      }

      // Validate schema and constraints
      const validatedResult = validateAndEnforceAssistantConstraints(parsedRaw, input);

      const durationMs = Date.now() - startTime;
      logAssistantEvent('info', 'AI evaluation suggestion generated successfully', {
        durationMs,
        suggestedMarks: validatedResult.suggestedMarks,
        maximumMarks: input.maximumMarks,
        confidence: validatedResult.confidence,
        needsHumanReview: validatedResult.needsHumanReview,
        criteriaEvaluated: validatedResult.criteria.length,
      });

      return validatedResult;
    } catch (error: any) {
      const durationMs = Date.now() - startTime;
      logAssistantEvent('error', 'AI Evaluation Assistant execution failed', {
        error: error.message,
        durationMs,
        maximumMarks: input.maximumMarks,
        hasImage,
        hasOcr,
      });

      // Rule 8: AI failures must NOT block manual examiner marking
      return createFallbackResult(
        input,
        `AI copilot suggestion could not be completed (${error.message}). Examiner manual marking is required.`,
        'Automated analysis encountered an error.'
      );
    }
  }

  /**
   * Helper that orchestrates loading the Question, Rubric, and AnswerPage
   * for a specific evaluation and question number, then invokes the AI assistant.
   */
  public static async getAssistantSuggestionForEvaluationQuestion(
    evaluationId: string,
    questionNumber: number,
    pageNumber?: number
  ): Promise<EvaluationAssistantResult> {
    const evaluation = await Evaluation.findById(evaluationId);
    if (!evaluation) {
      throw new Error(`Evaluation '${evaluationId}' not found`);
    }

    const answerBook = await AnswerBook.findById(evaluation.answerBookId).populate('examId');
    if (!answerBook) {
      throw new Error(`AnswerBook '${evaluation.answerBookId}' not found`);
    }

    const examId =
      typeof answerBook.examId === 'object' && answerBook.examId !== null && '_id' in (answerBook.examId as any)
        ? (answerBook.examId as any)._id
        : answerBook.examId;

    // Fetch official question
    const question = await Question.findOne({ examId, questionNumber });
    if (!question) {
      throw new Error(`Question Q${questionNumber} not found for exam '${examId}'`);
    }

    // Fetch page image and OCR if available
    let answerPage = null;
    if (pageNumber) {
      answerPage = await AnswerPage.findOne({
        answerBookId: answerBook._id,
        pageNumber,
      });
    } else {
      // Default to question number page or first page if not specified
      answerPage =
        (await AnswerPage.findOne({ answerBookId: answerBook._id, pageNumber: questionNumber })) ||
        (await AnswerPage.findOne({ answerBookId: answerBook._id }).sort({ pageNumber: 1 }));
    }

    const exam = await Exam.findById(examId);

    const input: EvaluationAssistantInput = {
      question: question.text,
      maximumMarks: question.maximumMarks,
      rubric: question.rubric.map((r) => ({
        criterion: r.criterion,
        marks: r.marks,
      })),
      referenceAnswer: question.referenceAnswer,
      keyConcepts: question.keyConcepts,
      gradingNotes: question.gradingNotes,
      language: question.evaluationLanguage,
      studentAnswerImage: answerPage?.cloudinary?.secureUrl,
      studentAnswerImageMimeType:
        answerPage?.cloudinary?.format === 'pdf' ? 'application/pdf' : 'image/jpeg',
      ocrText: answerPage?.ocr?.text,
      ocrConfidence: answerPage?.ocr?.confidence,
    };

    return this.evaluateStudentAnswer(input);
  }
}
