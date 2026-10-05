import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../lib/apiClient';
import { Exam } from '@evalnexa/types';

interface Preset {
  name: string;
  scripts: number;
  examiners: number;
  pace: number;
  moderators: number;
  modSamplePct: number;
  modPace: number;
  workDaysPerWeek: number;
}

const PRESETS: Preset[] = [
  {
    name: 'Midterm Tripos',
    scripts: 2400,
    examiners: 12,
    pace: 20,
    moderators: 2,
    modSamplePct: 10,
    modPace: 25,
    workDaysPerWeek: 5,
  },
  {
    name: 'University Final Board',
    scripts: 8500,
    examiners: 30,
    pace: 22,
    moderators: 4,
    modSamplePct: 15,
    modPace: 30,
    workDaysPerWeek: 6,
  },
  {
    name: 'High-Volume Foundation',
    scripts: 18000,
    examiners: 45,
    pace: 25,
    moderators: 5,
    modSamplePct: 10,
    modPace: 35,
    workDaysPerWeek: 6,
  },
];

export function TimelineSimulatorPage() {
  // Simulator Inputs
  const [totalScripts, setTotalScripts] = useState<number>(5000);
  const [activeExaminers, setActiveExaminers] = useState<number>(20);
  const [evalPace, setEvalPace] = useState<number>(25); // scripts/examiner/day
  const [activeModerators, setActiveModerators] = useState<number>(3);
  const [modSamplePct, setModSamplePct] = useState<number>(10); // % of scripts sampled
  const [modPace, setModPace] = useState<number>(30); // scripts/moderator/day
  const [workDaysPerWeek, setWorkDaysPerWeek] = useState<number>(6); // 5 or 6
  const [startDateStr, setStartDateStr] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [copiedMemo, setCopiedMemo] = useState(false);

  // Optional: load real examination to pre-populate total scripts
  const { data: examsData } = useQuery<{ success: boolean; data: Exam[] }>({
    queryKey: ['exams-list'],
    queryFn: async () => {
      const res = await apiClient.get('/exams');
      return res.data;
    },
  });

  const exams = examsData?.data || [];

  // ==========================================
  // MATHEMATICAL ENGINE (Pure & Fast)
  // ==========================================
  const simulation = useMemo(() => {
    const scripts = Math.max(1, totalScripts);
    const examiners = Math.max(1, activeExaminers);
    const pace = Math.max(1, evalPace);
    const moderators = Math.max(1, activeModerators);
    const modPct = Math.max(1, Math.min(100, modSamplePct));
    const mPace = Math.max(1, modPace);

    // 1. Evaluation Phase
    const dailyEvalCapacity = examiners * pace;
    const evalWorkingDays = Math.ceil(scripts / dailyEvalCapacity);
    const scriptsPerExaminer = Math.round(scripts / examiners);

    // 2. Moderation Phase
    const modScriptsTotal = Math.ceil((scripts * modPct) / 100);
    const dailyModCapacity = moderators * mPace;
    const modWorkingDays = Math.ceil(modScriptsTotal / dailyModCapacity);

    // Incoming moderation demand per day while evaluation is running
    const dailyModIncoming = Math.ceil((dailyEvalCapacity * modPct) / 100);
    const modCapacityRatio = dailyModCapacity / Math.max(1, dailyModIncoming);

    // 3. Overall Pipeline Duration
    // Moderation begins after day 1 of evaluation once initial batch is completed.
    // If moderation capacity >= daily incoming demand, moderation lags by ~1 day after evaluation ends.
    // If moderation capacity < daily incoming demand, moderation accumulates backlog and becomes bottleneck!
    let totalWorkingDays = evalWorkingDays + 1; // 1 day final audit/gazetting
    let bottleneckType: 'EVALUATION' | 'MODERATION' | 'EXAMINER_LOAD' | 'BALANCED' = 'BALANCED';
    let bottleneckTitle = 'Pipeline Synchronized';
    let bottleneckDesc = 'Examiner capacity and moderation throughput are well balanced. No structural delays detected.';
    let bottleneckSeverity: 'emerald' | 'amber' | 'crimson' = 'emerald';

    if (modCapacityRatio < 0.95) {
      // Moderation backlog choke
      const modBacklogLagDays = Math.ceil(modScriptsTotal / dailyModCapacity) - evalWorkingDays;
      if (modBacklogLagDays > 0) {
        totalWorkingDays = evalWorkingDays + modBacklogLagDays + 1;
      }
      bottleneckType = 'MODERATION';
      bottleneckSeverity = modCapacityRatio < 0.7 ? 'crimson' : 'amber';
      bottleneckTitle = `Moderation Deficit (${Math.round((1 - modCapacityRatio) * 100)}% Under-Capacity)`;
      bottleneckDesc = `Examiners submit ~${dailyModIncoming} audited scripts/day, but ${moderators} moderators only clear ${dailyModCapacity}/day. Review queues will clog.`;
    } else if (evalWorkingDays > 20) {
      bottleneckType = 'EVALUATION';
      bottleneckSeverity = evalWorkingDays > 30 ? 'crimson' : 'amber';
      bottleneckTitle = `Prolonged Evaluation (${evalWorkingDays} Working Days)`;
      bottleneckDesc = `Evaluation timeline is stretched. Expanding examiner pool from ${examiners} to ${examiners + 6} would cut delivery by ${Math.max(1, evalWorkingDays - Math.ceil(scripts / ((examiners + 6) * pace)))} days.`;
    } else if (pace > 35) {
      bottleneckType = 'EXAMINER_LOAD';
      bottleneckSeverity = 'amber';
      bottleneckTitle = `Aggressive Examiner Pace (${pace} scripts/day)`;
      bottleneckDesc = `Pace exceeds recommended cognitive threshold (30 scripts/day). Elevates risk of marking variance and student appeals.`;
    }

    // 4. Calendar Date Calculation (skipping weekend days)
    const startDate = new Date(startDateStr);
    let curr = new Date(startDate);
    let daysCounted = 0;

    while (daysCounted < totalWorkingDays) {
      curr.setDate(curr.getDate() + 1);
      const dayOfWeek = curr.getDay(); // 0 is Sun, 6 is Sat
      const isWorkDay = workDaysPerWeek === 6 ? dayOfWeek !== 0 : dayOfWeek !== 0 && dayOfWeek !== 6;
      if (isWorkDay) {
        daysCounted++;
      }
    }

    const completionDateFormatted = curr.toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });

    // 5. What-If Scenarios (Actionable recommendations)
    const whatIfAddExaminers = Math.ceil(scripts / ((examiners + 5) * pace));
    const daysSavedWithExaminers = Math.max(0, evalWorkingDays - whatIfAddExaminers);

    const whatIfPaceDown = Math.ceil(scripts / (examiners * Math.max(5, pace - 5)));
    const daysLostWithPaceDrop = whatIfPaceDown - evalWorkingDays;

    const whatIfModDouble = Math.ceil((scripts * ((modPct + 10) / 100)) / dailyModCapacity);

    return {
      dailyEvalCapacity,
      evalWorkingDays,
      scriptsPerExaminer,
      modScriptsTotal,
      dailyModCapacity,
      modWorkingDays,
      dailyModIncoming,
      modCapacityRatio,
      totalWorkingDays,
      bottleneckType,
      bottleneckTitle,
      bottleneckDesc,
      bottleneckSeverity,
      completionDateFormatted,
      calendarDays: Math.ceil((curr.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)),
      whatIf: {
        daysSavedWithExaminers,
        daysLostWithPaceDrop,
        whatIfModDouble,
      },
    };
  }, [totalScripts, activeExaminers, evalPace, activeModerators, modSamplePct, modPace, workDaysPerWeek, startDateStr]);

  const handleApplyPreset = (p: Preset) => {
    setTotalScripts(p.scripts);
    setActiveExaminers(p.examiners);
    setEvalPace(p.pace);
    setActiveModerators(p.moderators);
    setModSamplePct(p.modSamplePct);
    setModPace(p.modPace);
    setWorkDaysPerWeek(p.workDaysPerWeek);
  };

  const handleCopyMemo = () => {
    const text = `EVALNEXA DOCKET // TIMELINE SIMULATION REPORT
--------------------------------------------------
Total Scripts: ${totalScripts.toLocaleString()}
Examiners: ${activeExaminers} @ ${evalPace} scripts/day
Moderators: ${activeModerators} (${modSamplePct}% sample @ ${modPace}/day)
Working Days: ${simulation.totalWorkingDays} days (${workDaysPerWeek}-day week)
Projected Completion: ${simulation.completionDateFormatted}
Primary Bottleneck: ${simulation.bottleneckTitle}
--------------------------------------------------
Generated by EvalNexa Control Center on ${new Date().toLocaleDateString()}`;

    navigator.clipboard.writeText(text);
    setCopiedMemo(true);
    setTimeout(() => setCopiedMemo(false), 2500);
  };

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto' }}>
      {/* Editorial Header */}
      <div className="page-header" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <div className="page-header__eyebrow">
            EVALNEXA ARCHIVAL DOCKET // PREDICTIVE CADENCE
          </div>
          <h1 className="page-header__title">
            Examination Timeline <em>Simulator.</em>
          </h1>
          <p className="page-header__subtitle">
            Simulate operational throughput across script registration, marking capacity, and moderation queues. Detect pipeline bottlenecks before gazetting commitments.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-4)' }}>
          {PRESETS.map((p) => (
            <button
              key={p.name}
              type="button"
              className="btn btn-ghost"
              style={{
                fontSize: '11px',
                padding: '6px 12px',
                border: '1px solid var(--border)',
                background: 'var(--parchment-warm)',
              }}
              onClick={() => handleApplyPreset(p)}
            >
              Preset: {p.name}
            </button>
          ))}
          {exams.length > 0 && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ fontSize: '11px', padding: '6px 12px' }}
              onClick={() => setTotalScripts(exams[0].totalQuestions ? exams[0].totalQuestions * 150 : 3500)}
            >
              Load Active Exam Scope
            </button>
          )}
        </div>
      </div>

      {/* TOP PREDICTIVE EXECUTIVE SUMMARY BANNER */}
      <div
        className="folio-card"
        style={{
          marginBottom: 'var(--space-6)',
          borderLeft: `5px solid ${
            simulation.bottleneckSeverity === 'crimson'
              ? 'var(--crimson)'
              : simulation.bottleneckSeverity === 'amber'
              ? 'var(--gold)'
              : 'var(--bronze)'
          }`,
        }}
      >
        <div className="folio-card__body" style={{ padding: 'var(--space-6)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-6)', alignItems: 'center' }}>
            
            {/* Projected Date */}
            <div>
              <div className="label-caps" style={{ color: 'var(--gold)', letterSpacing: '0.14em', marginBottom: 4 }}>
                PROJECTED COMPLETION FOLIO
              </div>
              <div style={{ fontSize: '26px', fontWeight: 700, color: 'var(--navy)', lineHeight: 1.15, fontFamily: 'var(--font-serif)' }}>
                {simulation.completionDateFormatted}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 4 }}>
                <strong>{simulation.totalWorkingDays}</strong> Working Days · {simulation.calendarDays} Calendar Days
              </div>
            </div>

            {/* Identified Bottleneck */}
            <div style={{ borderLeft: '1px solid var(--rule)', paddingLeft: 'var(--space-5)' }}>
              <div className="label-caps" style={{ color: 'var(--gold)', letterSpacing: '0.14em', marginBottom: 4 }}>
                IDENTIFIED BOTTLENECK
              </div>
              <div
                style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  color:
                    simulation.bottleneckSeverity === 'crimson'
                      ? 'var(--crimson)'
                      : simulation.bottleneckSeverity === 'amber'
                      ? 'var(--gold)'
                      : '#10B981',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <span>{simulation.bottleneckSeverity === 'emerald' ? '✓' : '⚠'}</span>
                <span>{simulation.bottleneckTitle}</span>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--charcoal)', marginTop: 4, lineHeight: 1.4 }}>
                {simulation.bottleneckDesc}
              </div>
            </div>

            {/* Daily Throughput */}
            <div style={{ borderLeft: '1px solid var(--rule)', paddingLeft: 'var(--space-5)' }}>
              <div className="label-caps" style={{ color: 'var(--gold)', letterSpacing: '0.14em', marginBottom: 4 }}>
                DAILY HARVEST THROUGHPUT
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--ink)' }}>
                {simulation.dailyEvalCapacity.toLocaleString()} <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-muted)' }}>scripts/day</span>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 4 }}>
                ~{simulation.scriptsPerExaminer.toLocaleString()} scripts assigned per examiner
              </div>
            </div>

            {/* Copy Docket Button */}
            <div style={{ textAlign: 'right' }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleCopyMemo}
                style={{ width: '100%', padding: '12px 16px' }}
              >
                {copiedMemo ? '✓ Docket Copied' : 'Export Audit Memo'}
              </button>
            </div>

          </div>
        </div>
      </div>

      {/* MAIN TWO-COLUMN WORKSPACE */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 1.35fr', gap: 'var(--space-6)' }}>
        
        {/* LEFT COLUMN: SIMULATOR CONTROLS */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          
          {/* Section 1: Examination & Examiner Parameters */}
          <div className="folio-card">
            <div className="folio-card__header">
              <div className="folio-card__eyebrow">STAGE 01 // ON-SCREEN EVALUATION CADENCE</div>
              <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--navy)', margin: 0 }}>
                Examiner Pool Parameters
              </h2>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
              
              {/* Total Scripts */}
              <div className="form-field">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="form-label" htmlFor="inp-scripts">1. TOTAL CANDIDATE SCRIPTS</label>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--navy)' }}>
                    {totalScripts.toLocaleString()}
                  </span>
                </div>
                <input
                  id="inp-scripts"
                  type="range"
                  min={200}
                  max={25000}
                  step={100}
                  value={totalScripts}
                  onChange={(e) => setTotalScripts(Number(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  {[1500, 3000, 5000, 10000, 20000].map((num) => (
                    <button
                      key={num}
                      type="button"
                      onClick={() => setTotalScripts(num)}
                      style={{
                        padding: '2px 8px',
                        fontSize: '10px',
                        border: '1px solid var(--rule)',
                        background: totalScripts === num ? 'var(--navy)' : 'var(--parchment-warm)',
                        color: totalScripts === num ? '#fff' : 'inherit',
                        cursor: 'pointer',
                      }}
                    >
                      {num.toLocaleString()}
                    </button>
                  ))}
                </div>
              </div>

              <div className="copperplate-rule" style={{ margin: '4px 0' }} />

              {/* Active Examiners */}
              <div className="form-field">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="form-label" htmlFor="inp-examiners">2. ACCREDITED EXAMINERS ALLOCATED</label>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--navy)' }}>
                    {activeExaminers} Examiners
                  </span>
                </div>
                <input
                  id="inp-examiners"
                  type="range"
                  min={2}
                  max={80}
                  step={1}
                  value={activeExaminers}
                  onChange={(e) => setActiveExaminers(Number(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
              </div>

              {/* Evaluation Pace */}
              <div className="form-field">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="form-label" htmlFor="inp-pace">3. EVALUATION PACE (SCRIPTS / EXAMINER / DAY)</label>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--burgundy)' }}>
                    {evalPace} scripts/day
                  </span>
                </div>
                <input
                  id="inp-pace"
                  type="range"
                  min={5}
                  max={50}
                  step={1}
                  value={evalPace}
                  onChange={(e) => setEvalPace(Number(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  Standard institutional guideline: 18 – 28 scripts per examiner daily.
                </div>
              </div>

            </div>
          </div>

          {/* Section 2: Moderation & Calendar Parameters */}
          <div className="folio-card">
            <div className="folio-card__header">
              <div className="folio-card__eyebrow">STAGE 02 // GOVERNANCE & MODERATION REVIEW</div>
              <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--navy)', margin: 0 }}>
                Moderation & Schedule Discipline
              </h2>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
              
              {/* Moderation Sample Rate */}
              <div className="form-field">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="form-label" htmlFor="inp-mod-sample">4. MODERATION SAMPLE SAMPLING RATE</label>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--gold)' }}>
                    {modSamplePct}% ({simulation.modScriptsTotal} scripts)
                  </span>
                </div>
                <input
                  id="inp-mod-sample"
                  type="range"
                  min={5}
                  max={30}
                  step={1}
                  value={modSamplePct}
                  onChange={(e) => setModSamplePct(Number(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
              </div>

              {/* Active Moderators */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div className="form-field">
                  <label className="form-label" htmlFor="inp-mod-count">5. SENIOR MODERATORS</label>
                  <input
                    id="inp-mod-count"
                    type="number"
                    min={1}
                    max={20}
                    value={activeModerators}
                    onChange={(e) => setActiveModerators(Number(e.target.value))}
                    className="form-input"
                  />
                </div>

                <div className="form-field">
                  <label className="form-label" htmlFor="inp-mod-pace">6. MODERATOR PACE</label>
                  <input
                    id="inp-mod-pace"
                    type="number"
                    min={5}
                    max={80}
                    value={modPace}
                    onChange={(e) => setModPace(Number(e.target.value))}
                    className="form-input"
                  />
                </div>
              </div>

              {/* Working Days & Start Date */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div className="form-field">
                  <label className="form-label" htmlFor="inp-work-week">7. WORKING WEEK</label>
                  <select
                    id="inp-work-week"
                    value={workDaysPerWeek}
                    onChange={(e) => setWorkDaysPerWeek(Number(e.target.value))}
                    className="form-select"
                  >
                    <option value={5}>5 Days (Mon – Fri)</option>
                    <option value={6}>6 Days (Mon – Sat)</option>
                  </select>
                </div>

                <div className="form-field">
                  <label className="form-label" htmlFor="inp-start-date">8. COMMENCEMENT DATE</label>
                  <input
                    id="inp-start-date"
                    type="date"
                    value={startDateStr}
                    onChange={(e) => setStartDateStr(e.target.value)}
                    className="form-input"
                  />
                </div>
              </div>

            </div>
          </div>

        </div>

        {/* RIGHT COLUMN: TIMELINE GANTT & BOTTLENECK ANALYSIS */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          
          {/* Visual Gantt Bar */}
          <div className="folio-card">
            <div className="folio-card__header">
              <div className="folio-card__eyebrow">PIPELINE PROJECTION // STAGE CADENCE</div>
              <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--navy)', margin: 0 }}>
                Operational Phase Forecast
              </h2>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-5)' }}>
              
              {/* Progress Stage Representation */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                
                {/* Stage 1: Marking */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>1. Script Evaluation Phase ({activeExaminers} Examiners)</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--navy)' }}>
                      Days 1 – {simulation.evalWorkingDays} ({simulation.evalWorkingDays} Working Days)
                    </span>
                  </div>
                  <div style={{ height: 18, background: 'var(--parchment-warm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${Math.min(100, (simulation.evalWorkingDays / simulation.totalWorkingDays) * 100)}%`,
                        background: 'var(--navy)',
                      }}
                    />
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
                    Clears {simulation.dailyEvalCapacity} scripts daily across {activeExaminers} active allocation pools.
                  </div>
                </div>

                {/* Stage 2: Moderation */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>2. Moderation & Verification ({activeModerators} Reviewers)</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--gold)' }}>
                      Days 2 – {simulation.totalWorkingDays - 1} ({simulation.modWorkingDays} Working Days)
                    </span>
                  </div>
                  <div style={{ height: 18, background: 'var(--parchment-warm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${Math.min(100, (simulation.modWorkingDays / simulation.totalWorkingDays) * 100)}%`,
                        background: 'var(--gold)',
                      }}
                    />
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
                    Samples {modSamplePct}% ({simulation.modScriptsTotal} scripts). Throughput: {simulation.dailyModCapacity} scripts/day.
                  </div>
                </div>

                {/* Stage 3: Gazetting */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>3. Final Result Audit & Gazetting</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--burgundy)' }}>
                      Day {simulation.totalWorkingDays}
                    </span>
                  </div>
                  <div style={{ height: 18, background: 'var(--parchment-warm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: '100%', background: 'var(--burgundy)' }} />
                  </div>
                </div>

              </div>

            </div>
          </div>

          {/* Deep Bottleneck Analysis Dossier */}
          <div className="folio-card">
            <div className="folio-card__header">
              <div className="folio-card__eyebrow">DIAGNOSTIC MATRIX // THROUGHPUT RATIOS</div>
              <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--navy)', margin: 0 }}>
                Bottleneck & Capacity Ratios
              </h2>
            </div>
            <div className="folio-card__body" style={{ padding: 'var(--space-5)' }}>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
                <div style={{ padding: 'var(--space-4)', background: 'var(--parchment-warm)', border: '1px solid var(--rule)' }}>
                  <div className="label-caps" style={{ color: 'var(--text-muted)' }}>INCOMING MODERATION DEMAND</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--ink)', margin: '4px 0' }}>
                    {simulation.dailyModIncoming} <span style={{ fontSize: '12px', fontWeight: 400 }}>scripts/day</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {modSamplePct}% of {simulation.dailyEvalCapacity} evaluated
                  </div>
                </div>

                <div style={{ padding: 'var(--space-4)', background: 'var(--parchment-warm)', border: '1px solid var(--rule)' }}>
                  <div className="label-caps" style={{ color: 'var(--text-muted)' }}>MODERATION CAPACITY</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--navy)', margin: '4px 0' }}>
                    {simulation.dailyModCapacity} <span style={{ fontSize: '12px', fontWeight: 400 }}>scripts/day</span>
                  </div>
                  <div style={{ fontSize: '11px', color: simulation.modCapacityRatio < 1 ? 'var(--crimson)' : 'var(--bronze)' }}>
                    {Math.round(simulation.modCapacityRatio * 100)}% capacity coverage
                  </div>
                </div>
              </div>

              {/* What-if Optimization Options */}
              <div className="label-caps" style={{ color: 'var(--gold)', letterSpacing: '0.12em', marginBottom: 8 }}>
                SENSITIVITY & WHAT-IF LEVERS
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--parchment-card)', border: '1px solid var(--border)' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>Enlist +5 Examiners (Pool: {activeExaminers + 5})</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Expands evaluation capacity to {(activeExaminers + 5) * evalPace} scripts/day.</div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#1c5e32' }}>
                    -{simulation.whatIf.daysSavedWithExaminers} Days Faster
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--parchment-card)', border: '1px solid var(--border)' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>Examiner Fatigue / Pace Drops to {Math.max(5, evalPace - 5)}/day</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Simulates holiday drop-off or complex answer books.</div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--crimson)' }}>
                    +{simulation.whatIf.daysLostWithPaceDrop} Days Delay
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--parchment-card)', border: '1px solid var(--border)' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>Increase Moderation to 20% Double-Audit</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Doubles quality inspection depth for high-stakes papers.</div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--gold)' }}>
                    Requires {Math.ceil((totalScripts * 0.2) / simulation.dailyModCapacity)} Mod Days
                  </span>
                </div>

              </div>

            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
