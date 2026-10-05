import http from 'http';
import app from './app';
import { config } from './config';
import { connectDatabase } from './config/database';
import { initializeSocket } from './sockets';
import { EvaluationAssistantService } from './services/EvaluationAssistantService';

async function main() {
  await connectDatabase();

  const httpServer = http.createServer(app);
  initializeSocket(httpServer);

  httpServer.listen(config.port, () => {
    const aiStatus = EvaluationAssistantService.getConfigurationStatus();
    console.log(`\n╔══════════════════════════════════════════════╗`);
    console.log(`║         EvalNexa API Server                  ║`);
    console.log(`║  Port   : http://localhost:${config.port}              ║`);
    console.log(`║  Env    : ${config.nodeEnv.padEnd(35)}║`);
    console.log(`║  Gemini : Key Present=${String(aiStatus.hasApiKey).padEnd(5)} Model=${aiStatus.resolvedModel.padEnd(16)}║`);
    console.log(`╚══════════════════════════════════════════════╝\n`);
  });

  process.on('SIGTERM', () => {
    console.log('[Server] SIGTERM received – shutting down gracefully');
    httpServer.close(() => process.exit(0));
  });
}

main().catch((err) => {
  console.error('[Server] Fatal startup error:', err);
  process.exit(1);
});
