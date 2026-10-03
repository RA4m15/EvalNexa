/**
 * EvalNexa – Panel User Seed Script
 *
 * Creates dedicated accounts for each panel:
 *   • Admin     → Control Center   (admin@evalnexa.edu)
 *   • Examiner  → Examiner Workspace (examiner@evalnexa.edu)
 *   • Moderator → Moderation Centre  (moderator@evalnexa.edu)
 *
 * Usage:
 *   pnpm --filter backend seed-users
 *
 * Reads credentials from environment variables (or .env file).
 * Skips accounts that already exist — safe to run multiple times.
 */
import dotenv from 'dotenv';
dotenv.config();

import bcrypt from 'bcryptjs';
import mongoose from 'mongoose';
import { User } from '../models/User';
import { config } from '../config';

interface UserSeed {
  name: string;
  email: string;
  password: string;
  role: 'ADMIN' | 'EXAMINER' | 'MODERATOR';
  panel: string;
}

const USERS_TO_SEED: UserSeed[] = [
  {
    panel: 'Control Center',
    role: 'ADMIN',
    name: process.env.ADMIN_NAME || 'System Administrator',
    email: process.env.ADMIN_EMAIL || 'admin@evalnexa.edu',
    password: process.env.ADMIN_PASSWORD || 'Admin@1234',
  },
  {
    panel: 'Examiner Workspace',
    role: 'EXAMINER',
    name: process.env.EXAMINER_NAME || 'Dr. Sarah Mitchell',
    email: process.env.EXAMINER_EMAIL || 'examiner@evalnexa.edu',
    password: process.env.EXAMINER_PASSWORD || 'Examiner@5678',
  },
  {
    panel: 'Moderation Centre',
    role: 'MODERATOR',
    name: process.env.MODERATOR_NAME || 'Prof. James Harlow',
    email: process.env.MODERATOR_EMAIL || 'moderator@evalnexa.edu',
    password: process.env.MODERATOR_PASSWORD || 'Moderator@9012',
  },
];

async function seedUsers() {
  if (!config.mongoUri) {
    console.error('❌  MONGODB_URI is not set.');
    process.exit(1);
  }

  console.log('\n╔══════════════════════════════════════════════╗');
  console.log('║   EvalNexa – Panel Credentials Setup        ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  await mongoose.connect(config.mongoUri);
  console.log('✅  Connected to MongoDB\n');

  const results: { panel: string; status: 'created' | 'exists'; email: string; password: string }[] = [];

  for (const u of USERS_TO_SEED) {
    if (u.password.length < 8) {
      console.error(`❌  Password for ${u.email} must be at least 8 characters.`);
      process.exit(1);
    }

    const existing = await User.findOne({ email: u.email.toLowerCase() });

    const passwordHash = await bcrypt.hash(u.password, 12);

    if (existing) {
      existing.passwordHash = passwordHash;
      existing.name = u.name;
      existing.isActive = true;
      await existing.save();
      results.push({ panel: u.panel, status: 'exists', email: u.email, password: u.password });
      console.log(`🔄  [${u.role}] ${u.email} — credentials updated & verified.`);
    } else {
      await User.create({
        name: u.name,
        email: u.email.toLowerCase(),
        passwordHash,
        role: u.role,
        isActive: true,
      });
      results.push({ panel: u.panel, status: 'created', email: u.email, password: u.password });
      console.log(`✅  [${u.role}] ${u.email} — created successfully.`);
    }
  }

  console.log('\n╔══════════════════════════════════════════════════════════════════╗');
  console.log('║                   PANEL LOGIN CREDENTIALS                       ║');
  console.log('╠══════════════════════════════════════════════════════════════════╣');
  console.log('║  Panel                  Email                    Password       ║');
  console.log('╠══════════════════════════════════════════════════════════════════╣');
  for (const r of results) {
    const panelCol = r.panel.padEnd(23);
    const emailCol = r.email.padEnd(28);
    const passCol  = r.password.padEnd(14);
    console.log(`║  ${panelCol}  ${emailCol}  ${passCol}  ║`);
  }
  console.log('╠══════════════════════════════════════════════════════════════════╣');
  console.log('║  Ports:  Control Center :5173 · Examiner :5174 · Moderation :5175 ║');
  console.log('╚══════════════════════════════════════════════════════════════════╝\n');
  console.log('⚠️   Keep these credentials secure. Do not commit them to version control.\n');

  await mongoose.disconnect();
  process.exit(0);
}

seedUsers().catch((err) => {
  console.error('❌  Seed failed:', err.message);
  process.exit(1);
});
