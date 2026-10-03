/**
 * EvalNexa – Secure Admin Creation Script
 *
 * Usage:
 *   pnpm --filter backend create-admin
 *
 * Configure via environment variables:
 *   ADMIN_NAME, ADMIN_EMAIL, ADMIN_PASSWORD
 *
 * Or pass interactively via prompts.
 */
import dotenv from 'dotenv';
dotenv.config();

import readline from 'readline';
import bcrypt from 'bcryptjs';
import mongoose from 'mongoose';
import { User } from '../models/User';
import { config } from '../config';

async function prompt(question: string): Promise<string> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

async function createAdmin() {
  if (!config.mongoUri) {
    console.error('❌  MONGODB_URI is not set. Please configure your .env file.');
    process.exit(1);
  }

  console.log('\n╔══════════════════════════════════════╗');
  console.log('║   EvalNexa – Admin Account Setup    ║');
  console.log('╚══════════════════════════════════════╝\n');

  await mongoose.connect(config.mongoUri);
  console.log('✅  Connected to MongoDB\n');

  const name =
    process.env.ADMIN_NAME || (await prompt('Admin Name: '));
  const email =
    process.env.ADMIN_EMAIL || (await prompt('Admin Email: '));
  const password =
    process.env.ADMIN_PASSWORD || (await prompt('Admin Password (min 8 chars): '));

  if (!name || !email || !password) {
    console.error('❌  All fields are required');
    process.exit(1);
  }

  if (password.length < 8) {
    console.error('❌  Password must be at least 8 characters');
    process.exit(1);
  }

  const existing = await User.findOne({ email: email.toLowerCase() });
  if (existing) {
    console.error(`❌  A user with email "${email}" already exists`);
    process.exit(1);
  }

  const passwordHash = await bcrypt.hash(password, 12);
  const admin = await User.create({
    name,
    email: email.toLowerCase(),
    passwordHash,
    role: 'ADMIN',
    isActive: true,
  });

  console.log('\n✅  Admin account created successfully!');
  console.log(`   ID    : ${admin._id}`);
  console.log(`   Name  : ${admin.name}`);
  console.log(`   Email : ${admin.email}`);
  console.log(`   Role  : ${admin.role}`);
  console.log('\n⚠️   Keep these credentials secure. Do not share your password.\n');

  await mongoose.disconnect();
  process.exit(0);
}

createAdmin().catch((err) => {
  console.error('❌  Admin creation failed:', err.message);
  process.exit(1);
});
