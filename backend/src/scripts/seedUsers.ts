/**
 * EvalNexa – Secure Production User Seed Script
 *
 * Provisions initial authenticated users for each panel in MongoDB:
 *   • ADMIN     → Control Center
 *   • EXAMINER  → Examiner Workspace
 *   • MODERATOR → Moderation Centre
 *
 * Reads credentials ONLY from environment variables:
 *   SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD
 *   SEED_EXAMINER_EMAIL, SEED_EXAMINER_PASSWORD
 *   SEED_MODERATOR_EMAIL, SEED_MODERATOR_PASSWORD
 *
 * Usage:
 *   pnpm --filter backend seed-users
 */
import dotenv from 'dotenv';
dotenv.config();

import bcrypt from 'bcryptjs';
import mongoose from 'mongoose';
import { User } from '../models/User';

interface UserSeedConfig {
  panel: string;
  role: 'ADMIN' | 'EXAMINER' | 'MODERATOR';
  name: string;
  email: string | undefined;
  password: string | undefined;
  emailEnvVar: string;
  passwordEnvVar: string;
}

const SEED_CONFIGS: UserSeedConfig[] = [
  {
    panel: 'Control Center',
    role: 'ADMIN',
    name: 'System Administrator',
    email: process.env.SEED_ADMIN_EMAIL || process.env.ADMIN_EMAIL,
    password: process.env.SEED_ADMIN_PASSWORD || process.env.ADMIN_PASSWORD,
    emailEnvVar: 'SEED_ADMIN_EMAIL',
    passwordEnvVar: 'SEED_ADMIN_PASSWORD',
  },
  {
    panel: 'Examiner Workspace',
    role: 'EXAMINER',
    name: 'Dr. Sarah Mitchell',
    email: process.env.SEED_EXAMINER_EMAIL || process.env.EXAMINER_EMAIL,
    password: process.env.SEED_EXAMINER_PASSWORD || process.env.EXAMINER_PASSWORD,
    emailEnvVar: 'SEED_EXAMINER_EMAIL',
    passwordEnvVar: 'SEED_EXAMINER_PASSWORD',
  },
  {
    panel: 'Moderation Centre',
    role: 'MODERATOR',
    name: 'Prof. James Harlow',
    email: process.env.SEED_MODERATOR_EMAIL || process.env.MODERATOR_EMAIL,
    password: process.env.SEED_MODERATOR_PASSWORD || process.env.MODERATOR_PASSWORD,
    emailEnvVar: 'SEED_MODERATOR_EMAIL',
    passwordEnvVar: 'SEED_MODERATOR_PASSWORD',
  },
];

async function seedUsers() {
  const mongoUri = process.env.MONGODB_URI;
  if (!mongoUri) {
    console.error('❌ MONGODB_URI is not set. Please configure MONGODB_URI in your environment.');
    process.exit(1);
  }

  // Validate environment variables
  for (const config of SEED_CONFIGS) {
    if (!config.email) {
      console.error(`❌ Missing environment variable ${config.emailEnvVar} for ${config.panel}.`);
      process.exit(1);
    }
    if (!config.password) {
      console.error(`❌ Missing environment variable ${config.passwordEnvVar} for ${config.panel}.`);
      process.exit(1);
    }
    if (config.password.length < 8) {
      console.error(`❌ Password provided in ${config.passwordEnvVar} must be at least 8 characters.`);
      process.exit(1);
    }
  }

  console.log('\n╔══════════════════════════════════════════════╗');
  console.log('║   EvalNexa – Panel Users Database Provision  ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  try {
    await mongoose.connect(mongoUri);
    console.log('✅ Connected to MongoDB\n');

    for (const config of SEED_CONFIGS) {
      const email = config.email!.toLowerCase().trim();
      const password = config.password!;
      const passwordHash = await bcrypt.hash(password, 12);

      const existing = await User.findOne({ email });

      if (existing) {
        existing.passwordHash = passwordHash;
        existing.role = config.role;
        existing.name = config.name;
        existing.isActive = true;
        await existing.save();
        console.log(`🔄 [${config.role}] ${email} — credentials updated safely in database.`);
      } else {
        await User.create({
          name: config.name,
          email,
          passwordHash,
          role: config.role,
          isActive: true,
        });
        console.log(`✅ [${config.role}] ${email} — provisioned new account in database.`);
      }
    }

    console.log('\n✅ All panel accounts provisioned successfully in MongoDB.');
  } catch (err: any) {
    console.error('❌ Database user seed error:', err.message);
    process.exit(1);
  } finally {
    await mongoose.disconnect();
  }

  process.exit(0);
}

seedUsers().catch((err) => {
  console.error('❌ Fatal seed error:', err);
  process.exit(1);
});
