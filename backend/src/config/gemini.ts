import { GoogleGenAI } from '@google/genai';

/**
 * Centralized Gemini Client Manager for EvalNexa
 * Ensures a single initialization path, reads strictly from process.env,
 * and never exposes API keys or secrets in logs or responses.
 */
class GeminiClientManager {
  private client: GoogleGenAI | null = null;
  private currentKey: string = '';

  /**
   * Returns the centralized GoogleGenAI instance or null if unconfigured.
   */
  public getClient(): GoogleGenAI | null {
    const apiKey = process.env.GEMINI_API_KEY?.trim() || '';
    if (!apiKey) {
      this.client = null;
      this.currentKey = '';
      return null;
    }

    if (!this.client || this.currentKey !== apiKey) {
      this.currentKey = apiKey;
      this.client = new GoogleGenAI({ apiKey });
    }

    return this.client;
  }

  /**
   * Safe configuration diagnostics (Never prints the API key)
   */
  public getConfigStatus(): {
    isConfigured: boolean;
    hasApiKey: boolean;
    configuredModel: string;
    resolvedModel: string;
  } {
    const apiKey = process.env.GEMINI_API_KEY?.trim();
    const hasApiKey = Boolean(apiKey && apiKey.length > 0);
    const configuredModel = process.env.GEMINI_MODEL?.trim() || 'not configured';
    const defaultModel = 'gemini-3.1-flash-lite';

    // Disallow invalid placeholder values like 'Gemini API Key'
    const resolvedModel =
      configuredModel &&
      !configuredModel.includes(' ') &&
      configuredModel !== 'Gemini API Key' &&
      configuredModel !== 'not configured'
        ? configuredModel
        : defaultModel;

    return {
      isConfigured: hasApiKey,
      hasApiKey,
      configuredModel,
      resolvedModel,
    };
  }

  /**
   * Deterministic candidate models for resilient fallback execution
   */
  public getCandidateModels(): string[] {
    const status = this.getConfigStatus();
    return [
      status.resolvedModel,
      'gemini-3.1-flash-lite',
      'gemini-flash-latest',
      'gemini-3.8-flash',
      'gemini-3-flash-preview',
      'gemini-2.5-flash',
      'gemini-1.5-flash',
    ].filter((m, idx, arr) => arr.indexOf(m) === idx);
  }
}

export const geminiManager = new GeminiClientManager();
