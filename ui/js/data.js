// SAMPLE DATA for the Task 4 UI skeleton.
// All values are fabricated. They follow the data contract from the team plan
// (source / test_case / execution / finding / report / review records).
//
// Loaded as a normal script so the app works by just opening index.html in a
// browser (no web server needed). Later, if Member 1 provides real JSON files,
// you can swap this file for fetch() calls.

const DATA = {
  testCases: [
    {
      id: "TC-1",
      title: "Normal case: EFZ end date after reported sick leave",
      criterion_id: "CRIT-1",
      kind: "normal",
      review_status: "approved",
      inputs: {
        current_sick_leave: "11.03.2026 - 10.04.2026",
        employment_end: "31.03.2026",
        prior_illness_reported: true
      },
      expected: { efz_end: "30.03.2026", reason: "End of continued pay (EFZ) after 6 weeks" },
      expected_basis: "Synthetic demo fixture — see SRC-1",
      review: { reviewer: "Human reviewer", decision: "approved", timestamp: "2026-10-26T10:00:00" }
    },
    {
      id: "TC-2",
      title: "Edge case: correction after late sick-note submission",
      criterion_id: "CRIT-1",
      kind: "edge",
      review_status: "approved",
      inputs: {
        storno_reason: "88",
        new_submission_reason: "01",
        efz_end_after_correction: "27.03.2026"
      },
      expected: { efz_end: "27.03.2026", storno_sent: true },
      expected_basis: "Synthetic demo fixture — see SRC-1",
      review: { reviewer: "Human reviewer", decision: "approved", timestamp: "2026-10-26T10:05:00" }
    },
    {
      id: "TC-3",
      title: "Invalid input: sick leave never reported to health insurer",
      criterion_id: "CRIT-2",
      kind: "invalid",
      review_status: "approved",
      inputs: {
        sick_leave_paper_only: "01.03.2026 - 03.03.2026",
        reported_to_insurer: false
      },
      expected: { result: "blocked / must not calculate benefit" },
      expected_basis: "Synthetic demo fixture — see SRC-1",
      review: { reviewer: "Human reviewer", decision: "approved", timestamp: "2026-10-26T10:10:00" }
    }
  ],

  executions: [
    {
      id: "RUN-1",
      test_case_id: "TC-1",
      vendor: "Demo only (fabricated)",
      software_version: "unknown",
      observed: { efz_end: "30.03.2026", reason: "End of continued pay (EFZ) after 6 weeks" },
      evidence_ref: "fabricated-output-runs/run-1.json"
    },
    {
      id: "RUN-2",
      test_case_id: "TC-2",
      vendor: "Demo only (fabricated)",
      software_version: "unknown",
      observed: { efz_end: "30.03.2026", storno_sent: true },
      evidence_ref: "fabricated-output-runs/run-2.json"
    }
    // NOTE: there is deliberately NO execution record for TC-3,
    // so TC-3 must show NOT EVALUATED, never a pass.
  ],

  findings: [
    {
      test_case_id: "TC-1",
      status: "PASS",
      reason: "Observed EFZ end matches expected value.",
      links: ["SRC-1", "REQ-1", "TC-1", "RUN-1"]
    },
    {
      test_case_id: "TC-2",
      status: "MISMATCH",
      reason: "Observed EFZ end 30.03.2026 differs from expected 27.03.2026.",
      links: ["SRC-1", "REQ-1", "TC-2", "RUN-2"]
    },
    {
      test_case_id: "TC-3",
      status: "NOT EVALUATED",
      reason: "No execution output exists for this test case.",
      links: ["SRC-1", "REQ-1", "TC-3"]
    }
  ],

  report: {
    id: "RPT-1",
    template_id: "TPL-1 (SYNTHETIC — illustrative, not the official form)",
    renderer_version: "demo-0.1",
    conformance: [
      { check: "required_fields", status: "pass" },
      { check: "field_order", status: "pass" },
      { check: "value_mapping", status: "fail", detail: "EFZ end date format differs from template" }
    ],
    findings: ["TC-1", "TC-2", "TC-3"],
    limitations: "Uses fabricated data only. Template is illustrative; no legal compliance claim."
  },

  sources: [
    {
      id: "SRC-1",
      title: "Synthetic demo fixture: sickness benefit with prior illness",
      issuer: "Team 10 demo",
      version: "v1",
      citation: "See refs/Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx (test constellation)"
    }
  ],

  requirements: [
    {
      id: "REQ-1",
      text: "Continued pay (EFZ) must end when the legal conditions end; corrections must cancel and re-issue the notification.",
      source_id: "SRC-1",
      citation: "fixture, p.1",
      status: "needs_review"
    }
  ],

  criteria: [
    {
      id: "CRIT-1",
      requirement_id: "REQ-1",
      text: "EFZ ends 30.03.2026 in the normal case; after a correction (Abgabegrund 88 + 01) it ends 27.03.2026.",
      status: "approved",
      approved_by: "Human reviewer"
    },
    {
      id: "CRIT-2",
      requirement_id: "REQ-1",
      text: "Sick leave that was never reported to the insurer must not lead to a benefit calculation.",
      status: "approved",
      approved_by: "Human reviewer"
    }
  ]
};
