# UAT Test Book

**Generated from the automated suite — do not edit by hand.**

```
python apps/api/scripts/generate_uat_book.py --out docs/42-uat-test-book.md
```

Every script below cites the test that proves it. A hand-written UAT book drifts: six 
weeks in, the tests have moved and the book has not, and the first person to find out is 
a tester following a script for behaviour that no longer exists. Deriving it means the 
book cannot describe something that is not tested, and a requirement with no test appears 
in §3 rather than being silently absent.

---

## 1. Summary

| | |
|---|---|
| Requirements with automated coverage | **70** |
| Generated scripts | **88** |
| Requirements needing manual acceptance | 6 |
| Requirements with no cited test | 0 |

### How to execute a script

Each script gives the role, the steps, and the expected result. Record **pass**, **fail** 
or **blocked** against the script number, with the tester's name and the date. A script 
marked `Automated by` also runs in CI on every change — executing it manually in UAT 
confirms the behaviour in MMBL's own environment with MMBL's own data, which is what UAT 
is actually for.

---

## 2. Scripts

### Scope of Work — RFP §4a(i)

#### SOW-01

**UAT-SOW-01-01** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)


#### SOW-02

**UAT-SOW-02-01** · Run the clause library suite

*Why it matters:* Clause library, alternatives, and the playbook policy engine.

*Automated by:* `test_clause_library.py` — 47 tests

<details><summary>Tests in this script</summary>

- `test_a_draft_clause_has_no_approved_wording` — A draft clause has no approved wording
- `test_submit_then_approve_freezes_a_version` — Submit then approve freezes a version
- `test_the_author_cannot_approve_their_own_clause` — The author cannot approve their own clause
- `test_an_empty_clause_cannot_be_submitted` — An empty clause cannot be submitted
- `test_approving_again_supersedes_the_previous_version` — Approving again supersedes the previous version
- `test_editing_approved_wording_sends_it_back_to_draft` — Editing approved wording sends it back to draft
- `test_retiring_takes_the_clause_and_its_versions_out_of_use` — Retiring takes the clause and its versions out of use
- `test_alternatives_are_ranked_fallbacks_of_their_parent` — Alternatives are ranked fallbacks of their parent
- `test_an_alternative_needs_approval_like_anything_else` — An alternative needs approval like anything else
- `test_references_are_found_in_order_without_duplicates` — References are found in order without duplicates
- `test_expand_inserts_the_approved_wording` — Expand inserts the approved wording
- `test_expand_uses_the_approved_snapshot_not_a_live_edit` — Expand uses the approved snapshot not a live edit
- `test_an_unresolvable_reference_is_reported_not_dropped` — An unresolvable reference is reported not dropped
- `test_an_unapproved_clause_does_not_resolve` — An unapproved clause does not resolve
- `test_validate_references_explains_both_failure_modes` — Validate references explains both failure modes
- `test_a_clause_may_itself_contain_merge_fields` — A clause may itself contain merge fields
- `test_a_template_cannot_be_approved_with_a_broken_reference` — A template cannot be approved with a broken reference
- `test_generation_refuses_when_a_clause_loses_its_approval` — Generation refuses when a clause loses its approval
- `test_a_playbook_only_applies_to_its_contract_type` — A playbook only applies to its contract type
- `test_a_house_wide_playbook_applies_to_everything` — A house wide playbook applies to everything
- `test_both_the_house_policy_and_the_type_policy_apply` — Both the house policy and the type policy apply
- `test_a_value_threshold_narrows_the_policy` — A value threshold narrows the policy
- `test_a_draft_playbook_does_not_apply` — A draft playbook does not apply
- `test_an_unchanged_clause_is_present` — An unchanged clause is present
- `test_formatting_alone_is_not_a_deviation` — Formatting alone is not a deviation
- `test_a_missing_clause_is_reported_as_missing` — A missing clause is reported as missing
- `test_an_edited_cap_is_reported_as_altered_with_a_diff` — An edited cap is reported as altered with a diff
- `test_prohibited_language_is_caught_when_present` — Prohibited language is caught when present
- `test_prohibited_language_that_is_absent_produces_no_finding` — Prohibited language that is absent produces no finding
- `test_the_same_rule_in_two_playbooks_is_one_finding` — The same rule in two playbooks is one finding
- `test_an_unapproved_clause_is_not_measured_against` — An unapproved clause is not measured against
- `test_a_blocking_deviation_classifies_the_agreement_non_standard` — A blocking deviation classifies the agreement non standard
- `test_a_warning_deviation_does_not_change_the_approval_route` — A warning deviation does not change the approval route
- `test_a_compliant_draft_passes_cleanly` — A compliant draft passes cleanly
- `test_a_generated_draft_is_compliant_with_the_policy_that_shaped_it` — A generated draft is compliant with the policy that shaped it
- `test_a_rule_naming_an_unknown_clause_is_rejected` — A rule naming an unknown clause is rejected
- `test_unknown_rule_kinds_and_severities_are_rejected` — Unknown rule kinds and severities are rejected
- `test_a_duplicated_rule_is_rejected` — A duplicated rule is rejected
- `test_the_seeded_demo_workspace_is_coherent_end_to_end` — The seeded demo workspace is coherent end to end
- `test_a_drafter_can_choose_a_pre_approved_fallback` — A drafter can choose a pre approved fallback
- `test_no_choice_means_the_preferred_wording` — No choice means the preferred wording
- `test_an_arbitrary_clause_cannot_be_swapped_in` — An arbitrary clause cannot be swapped in
- `test_an_unapproved_alternative_cannot_be_chosen` — An unapproved alternative cannot be chosen
- `test_an_optional_clause_can_be_appended` — An optional clause can be appended
- `test_the_wizard_is_told_the_options_and_their_risk` — The wizard is told the options and their risk
- `test_optional_clauses_exclude_what_the_template_already_uses` — Optional clauses exclude what the template already uses
- `test_a_chosen_fallback_still_satisfies_a_playbook_that_allows_it` — A chosen fallback still satisfies a playbook that allows it

</details>


#### SOW-03

**UAT-SOW-03-01** · Run the clause library suite

*Why it matters:* Clause library, alternatives, and the playbook policy engine.

*Automated by:* `test_clause_library.py` — 47 tests

<details><summary>Tests in this script</summary>

- `test_a_draft_clause_has_no_approved_wording` — A draft clause has no approved wording
- `test_submit_then_approve_freezes_a_version` — Submit then approve freezes a version
- `test_the_author_cannot_approve_their_own_clause` — The author cannot approve their own clause
- `test_an_empty_clause_cannot_be_submitted` — An empty clause cannot be submitted
- `test_approving_again_supersedes_the_previous_version` — Approving again supersedes the previous version
- `test_editing_approved_wording_sends_it_back_to_draft` — Editing approved wording sends it back to draft
- `test_retiring_takes_the_clause_and_its_versions_out_of_use` — Retiring takes the clause and its versions out of use
- `test_alternatives_are_ranked_fallbacks_of_their_parent` — Alternatives are ranked fallbacks of their parent
- `test_an_alternative_needs_approval_like_anything_else` — An alternative needs approval like anything else
- `test_references_are_found_in_order_without_duplicates` — References are found in order without duplicates
- `test_expand_inserts_the_approved_wording` — Expand inserts the approved wording
- `test_expand_uses_the_approved_snapshot_not_a_live_edit` — Expand uses the approved snapshot not a live edit
- `test_an_unresolvable_reference_is_reported_not_dropped` — An unresolvable reference is reported not dropped
- `test_an_unapproved_clause_does_not_resolve` — An unapproved clause does not resolve
- `test_validate_references_explains_both_failure_modes` — Validate references explains both failure modes
- `test_a_clause_may_itself_contain_merge_fields` — A clause may itself contain merge fields
- `test_a_template_cannot_be_approved_with_a_broken_reference` — A template cannot be approved with a broken reference
- `test_generation_refuses_when_a_clause_loses_its_approval` — Generation refuses when a clause loses its approval
- `test_a_playbook_only_applies_to_its_contract_type` — A playbook only applies to its contract type
- `test_a_house_wide_playbook_applies_to_everything` — A house wide playbook applies to everything
- `test_both_the_house_policy_and_the_type_policy_apply` — Both the house policy and the type policy apply
- `test_a_value_threshold_narrows_the_policy` — A value threshold narrows the policy
- `test_a_draft_playbook_does_not_apply` — A draft playbook does not apply
- `test_an_unchanged_clause_is_present` — An unchanged clause is present
- `test_formatting_alone_is_not_a_deviation` — Formatting alone is not a deviation
- `test_a_missing_clause_is_reported_as_missing` — A missing clause is reported as missing
- `test_an_edited_cap_is_reported_as_altered_with_a_diff` — An edited cap is reported as altered with a diff
- `test_prohibited_language_is_caught_when_present` — Prohibited language is caught when present
- `test_prohibited_language_that_is_absent_produces_no_finding` — Prohibited language that is absent produces no finding
- `test_the_same_rule_in_two_playbooks_is_one_finding` — The same rule in two playbooks is one finding
- `test_an_unapproved_clause_is_not_measured_against` — An unapproved clause is not measured against
- `test_a_blocking_deviation_classifies_the_agreement_non_standard` — A blocking deviation classifies the agreement non standard
- `test_a_warning_deviation_does_not_change_the_approval_route` — A warning deviation does not change the approval route
- `test_a_compliant_draft_passes_cleanly` — A compliant draft passes cleanly
- `test_a_generated_draft_is_compliant_with_the_policy_that_shaped_it` — A generated draft is compliant with the policy that shaped it
- `test_a_rule_naming_an_unknown_clause_is_rejected` — A rule naming an unknown clause is rejected
- `test_unknown_rule_kinds_and_severities_are_rejected` — Unknown rule kinds and severities are rejected
- `test_a_duplicated_rule_is_rejected` — A duplicated rule is rejected
- `test_the_seeded_demo_workspace_is_coherent_end_to_end` — The seeded demo workspace is coherent end to end
- `test_a_drafter_can_choose_a_pre_approved_fallback` — A drafter can choose a pre approved fallback
- `test_no_choice_means_the_preferred_wording` — No choice means the preferred wording
- `test_an_arbitrary_clause_cannot_be_swapped_in` — An arbitrary clause cannot be swapped in
- `test_an_unapproved_alternative_cannot_be_chosen` — An unapproved alternative cannot be chosen
- `test_an_optional_clause_can_be_appended` — An optional clause can be appended
- `test_the_wizard_is_told_the_options_and_their_risk` — The wizard is told the options and their risk
- `test_optional_clauses_exclude_what_the_template_already_uses` — Optional clauses exclude what the template already uses
- `test_a_chosen_fallback_still_satisfies_a_playbook_that_allows_it` — A chosen fallback still satisfies a playbook that allows it

</details>


#### SOW-04

**UAT-SOW-04-01** · Run the ai assist suite

*Why it matters:* AI assist — clause suggestion, data capture, and the confirmation gate.

*Automated by:* `test_ai_assist.py` — 25 tests

<details><summary>Tests in this script</summary>

- `test_a_policy_required_missing_clause_is_the_top_suggestion` — A policy required missing clause is the top suggestion
- `test_it_suggests_what_comparable_agreements_actually_use` — It suggests what comparable agreements actually use
- `test_a_clause_already_in_the_draft_is_not_suggested` — A clause already in the draft is not suggested
- `test_a_clause_referenced_in_the_body_is_not_suggested` — A clause referenced in the body is not suggested
- `test_high_risk_library_clauses_are_suggested_even_without_policy` — High risk library clauses are suggested even without policy
- `test_suggestions_are_deterministic` — Suggestions are deterministic
- `test_an_unapproved_clause_is_never_suggested` — An unapproved clause is never suggested
- `test_capture_writes_nothing_to_the_contract` — Capture writes nothing to the contract
- `test_the_capture_records_which_provider_produced_it` — The capture records which provider produced it
- `test_only_capturable_fields_are_stored` — Only capturable fields are stored
- `test_applying_writes_only_the_ticked_fields` — Applying writes only the ticked fields
- `test_a_field_that_was_never_offered_is_refused` — A field that was never offered is refused
- `test_a_capture_cannot_be_applied_twice` — A capture cannot be applied twice
- `test_accepting_nothing_discards_the_capture` — Accepting nothing discards the capture
- `test_discarding_leaves_the_contract_alone` — Discarding leaves the contract alone
- `test_a_date_that_cannot_be_parsed_is_refused_not_guessed` — A date that cannot be parsed is refused not guessed
- `test_a_captured_date_becomes_a_real_date` — A captured date becomes a real date
- `test_a_low_confidence_value_is_shown_but_not_pre_ticked` — A low confidence value is shown but not pre ticked
- `test_a_high_confidence_value_that_changes_nothing_is_not_pre_ticked` — A high confidence value that changes nothing is not pre ticked
- `test_a_high_confidence_change_is_pre_ticked` — A high confidence change is pre ticked
- `test_the_confirmation_is_audited_with_what_was_accepted` — The confirmation is audited with what was accepted
- `test_the_local_provider_is_selected_when_configured` — The local provider is selected when configured
- `test_local_falls_back_to_the_stub_without_an_endpoint` — Local falls back to the stub without an endpoint
- `test_an_unreadable_document_returns_nothing_rather_than_inventing_fields` — An unreadable document returns nothing rather than inventing fields
- `test_a_transport_failure_degrades_instead_of_exploding` — A transport failure degrades instead of exploding

</details>

**UAT-SOW-04-02** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)

**UAT-SOW-04-03** · Run the journeys e2e suite

*Why it matters:* End-to-end journey tests (Phase 10).

*Automated by:* `test_journeys_e2e.py` — 1 tests

<details><summary>Tests in this script</summary>

- `test_one_workspace_cannot_read_anothers_agreements` — One workspace cannot read anothers agreements

</details>

**UAT-SOW-04-04** · Run the merge fields suite

*Why it matters:* Merge fields, template approval, and generation.

*Automated by:* `test_merge_fields.py` — 58 tests

<details><summary>Tests in this script</summary>

- `test_placeholders_are_found_in_order_without_duplicates` — Placeholders are found in order without duplicates
- `test_definition_rejects_a_select_with_no_options` — Definition rejects a select with no options
- `test_definition_rejects_duplicate_and_malformed_keys` — Definition rejects duplicate and malformed keys
- `test_definition_flags_a_placeholder_no_field_supplies` — Definition flags a placeholder no field supplies
- `test_definition_accepts_contract_derived_placeholders` — Definition accepts contract derived placeholders
- `test_values_are_coerced_to_their_declared_type` — Values are coerced to their declared type
- `test_a_money_field_refuses_prose` — A money field refuses prose
- `test_a_select_refuses_a_value_outside_its_list` — A select refuses a value outside its list
- `test_multiselect_reports_every_invalid_choice_at_once` — Multiselect reports every invalid choice at once
- `test_numeric_bounds_are_enforced` — Numeric bounds are enforced
- `test_a_required_field_left_blank_is_an_error` — A required field left blank is an error
- `test_an_optional_field_left_blank_is_not` — An optional field left blank is not
- `test_a_default_fills_in_for_an_absent_value` — A default fills in for an absent value
- `test_unknown_submitted_keys_are_dropped_not_rejected` — Unknown submitted keys are dropped not rejected
- `test_render_substitutes_and_formats_deterministically` — Render substitutes and formats deterministically
- `test_render_is_stable_across_repeated_calls` — Render is stable across repeated calls
- `test_an_unfilled_placeholder_stays_visible_and_is_reported` — An unfilled placeholder stays visible and is reported
- `test_an_empty_value_counts_as_unresolved_rather_than_blanking_the_document` — An empty value counts as unresolved rather than blanking the document
- `test_template_fields_win_over_contract_derived_values` — Template fields win over contract derived values
- `test_multiselect_renders_as_a_readable_list` — Multiselect renders as a readable list
- `test_suggest_fields_scaffolds_from_a_pasted_body` — Suggest fields scaffolds from a pasted body
- `test_suggest_fields_skips_what_is_already_defined` — Suggest fields skips what is already defined
- `test_a_draft_template_cannot_generate` — A draft template cannot generate
- `test_submit_then_approve_freezes_a_version` — Submit then approve freezes a version
- `test_the_author_cannot_approve_their_own_template` — The author cannot approve their own template
- `test_an_author_role_cannot_approve_at_all` — An author role cannot approve at all
- `test_an_owner_may_approve_their_own_template_in_a_small_workspace` — An owner may approve their own template in a small workspace
- `test_a_template_with_an_unfillable_placeholder_cannot_be_submitted` — A template with an unfillable placeholder cannot be submitted
- `test_an_empty_template_cannot_be_submitted` — An empty template cannot be submitted
- `test_rejection_returns_it_to_draft_with_the_reason` — Rejection returns it to draft with the reason
- `test_editing_the_form_of_an_approved_template_un_approves_it` — Editing the form of an approved template un approves it
- `test_removing_a_field_the_body_still_uses_is_refused` — Removing a field the body still uses is refused
- `test_set_fields_refuses_a_definition_that_cannot_work` — Set fields refuses a definition that cannot work
- `test_approving_again_supersedes_the_previous_version` — Approving again supersedes the previous version
- `test_generation_uses_the_approved_snapshot_not_the_live_edit` — Generation uses the approved snapshot not the live edit
- `test_generation_refuses_when_a_required_field_is_missing` — Generation refuses when a required field is missing
- `test_generation_refuses_rather_than_leaving_a_gap` — Generation refuses rather than leaving a gap
- `test_allow_unresolved_is_an_explicit_opt_in` — Allow unresolved is an explicit opt in
- `test_generated_body_reads_correctly_end_to_end` — Generated body reads correctly end to end
- `test_retiring_takes_the_template_and_its_versions_out_of_use` — Retiring takes the template and its versions out of use
- `test_form_schema_reports_whether_the_template_is_usable` — Form schema reports whether the template is usable
- `test_preview_reports_errors_without_persisting_anything` — Preview reports errors without persisting anything
- `test_a_new_template_is_not_usable_until_approved` — A new template is not usable until approved
- `test_creating_a_template_with_a_broken_form_is_rejected` — Creating a template with a broken form is rejected
- `test_the_form_endpoint_describes_the_intake_screen` — The form endpoint describes the intake screen
- `test_preview_renders_without_creating_a_contract` — Preview renders without creating a contract
- `test_generate_creates_the_draft_and_records_the_template_revision` — Generate creates the draft and records the template revision
- `test_generate_rejects_a_value_outside_the_permitted_list` — Generate rejects a value outside the permitted list
- `test_generate_reports_every_missing_required_field_at_once` — Generate reports every missing required field at once
- `test_the_author_cannot_approve_their_own_template_over_the_api` — The author cannot approve their own template over the API
- `test_rejection_sends_it_back_with_the_reason` — Rejection sends it back with the reason
- `test_versions_list_the_approved_revisions_newest_first` — Versions list the approved revisions newest first
- `test_editing_approved_wording_takes_it_out_of_use` — Editing approved wording takes it out of use
- `test_suggest_fields_scaffolds_the_form_from_a_pasted_body` — Suggest fields scaffolds the form from a pasted body
- `test_a_retired_template_cannot_generate_over_the_api` — A retired template cannot generate over the API
- `test_a_template_from_another_tenant_is_invisible` — A template from another tenant is invisible
- `test_the_contract_records_which_template_revision_generated_it` — The contract records which template revision generated it
- `test_stored_values_render_identically_to_the_originals` — Stored values render identically to the originals

</details>


#### SOW-05

**UAT-SOW-05-01** · Run the docx roundtrip suite

*Why it matters:* Word round-trip — export, mark up in Word, import back.

*Automated by:* `test_docx_roundtrip.py` — 27 tests

<details><summary>Tests in this script</summary>

- `test_structure_survives_a_full_cycle` — Structure survives a full cycle
- `test_corpus_is_at_least_ten_agreements` — Corpus is at least ten agreements
- `test_a_second_cycle_changes_nothing_further` — A second cycle changes nothing further
- `test_numbers_are_word_numbering_not_typed_text` — Numbers are word numbering not typed text
- `test_depth_is_preserved_to_three_levels` — Depth is preserved to three levels
- `test_numbering_definition_is_cumulative` — Numbering definition is cumulative
- `test_import_reconstructs_depth_from_numbering_data` — Import reconstructs depth from numbering data
- `test_installing_numbering_twice_does_not_duplicate` — Installing numbering twice does not duplicate
- `test_insertions_and_deletions_are_both_captured` — Insertions and deletions are both captured
- `test_deleted_text_is_read_from_deltext` — Deleted text is read from deltext
- `test_author_and_timestamp_survive` — Author and timestamp survive
- `test_body_reflects_accepted_changes` — Body reflects accepted changes
- `test_changes_carry_their_paragraph_context` — Changes carry their paragraph context
- `test_summary_counts_are_right` — Summary counts are right
- `test_a_clean_document_reports_no_revisions` — A clean document reports no revisions
- `test_comments_are_read_with_author_and_text` — Comments are read with author and text
- `test_comments_are_anchored_to_their_clause` — Comments are anchored to their clause
- `test_comment_timestamps_survive` — Comment timestamps survive
- `test_document_without_comments_is_fine` — Document without comments is fine
- `test_tables_survive_the_cycle` — Tables survive the cycle
- `test_headings_keep_their_level` — Headings keep their level
- `test_bold_and_italic_become_runs` — Bold and italic become runs
- `test_header_carries_the_reference` — Header carries the reference
- `test_title_is_not_duplicated_when_the_body_has_one` — Title is not duplicated when the body has one
- `test_a_pdf_gets_a_useful_error` — A PDF gets a useful error
- `test_empty_bytes_do_not_crash` — Empty bytes do not crash
- `test_empty_body_exports_a_valid_document` — Empty body exports a valid document

</details>


#### SOW-06

**UAT-SOW-06-01** · Run the clause library suite

*Why it matters:* Clause library, alternatives, and the playbook policy engine.

*Automated by:* `test_clause_library.py` — 47 tests

<details><summary>Tests in this script</summary>

- `test_a_draft_clause_has_no_approved_wording` — A draft clause has no approved wording
- `test_submit_then_approve_freezes_a_version` — Submit then approve freezes a version
- `test_the_author_cannot_approve_their_own_clause` — The author cannot approve their own clause
- `test_an_empty_clause_cannot_be_submitted` — An empty clause cannot be submitted
- `test_approving_again_supersedes_the_previous_version` — Approving again supersedes the previous version
- `test_editing_approved_wording_sends_it_back_to_draft` — Editing approved wording sends it back to draft
- `test_retiring_takes_the_clause_and_its_versions_out_of_use` — Retiring takes the clause and its versions out of use
- `test_alternatives_are_ranked_fallbacks_of_their_parent` — Alternatives are ranked fallbacks of their parent
- `test_an_alternative_needs_approval_like_anything_else` — An alternative needs approval like anything else
- `test_references_are_found_in_order_without_duplicates` — References are found in order without duplicates
- `test_expand_inserts_the_approved_wording` — Expand inserts the approved wording
- `test_expand_uses_the_approved_snapshot_not_a_live_edit` — Expand uses the approved snapshot not a live edit
- `test_an_unresolvable_reference_is_reported_not_dropped` — An unresolvable reference is reported not dropped
- `test_an_unapproved_clause_does_not_resolve` — An unapproved clause does not resolve
- `test_validate_references_explains_both_failure_modes` — Validate references explains both failure modes
- `test_a_clause_may_itself_contain_merge_fields` — A clause may itself contain merge fields
- `test_a_template_cannot_be_approved_with_a_broken_reference` — A template cannot be approved with a broken reference
- `test_generation_refuses_when_a_clause_loses_its_approval` — Generation refuses when a clause loses its approval
- `test_a_playbook_only_applies_to_its_contract_type` — A playbook only applies to its contract type
- `test_a_house_wide_playbook_applies_to_everything` — A house wide playbook applies to everything
- `test_both_the_house_policy_and_the_type_policy_apply` — Both the house policy and the type policy apply
- `test_a_value_threshold_narrows_the_policy` — A value threshold narrows the policy
- `test_a_draft_playbook_does_not_apply` — A draft playbook does not apply
- `test_an_unchanged_clause_is_present` — An unchanged clause is present
- `test_formatting_alone_is_not_a_deviation` — Formatting alone is not a deviation
- `test_a_missing_clause_is_reported_as_missing` — A missing clause is reported as missing
- `test_an_edited_cap_is_reported_as_altered_with_a_diff` — An edited cap is reported as altered with a diff
- `test_prohibited_language_is_caught_when_present` — Prohibited language is caught when present
- `test_prohibited_language_that_is_absent_produces_no_finding` — Prohibited language that is absent produces no finding
- `test_the_same_rule_in_two_playbooks_is_one_finding` — The same rule in two playbooks is one finding
- `test_an_unapproved_clause_is_not_measured_against` — An unapproved clause is not measured against
- `test_a_blocking_deviation_classifies_the_agreement_non_standard` — A blocking deviation classifies the agreement non standard
- `test_a_warning_deviation_does_not_change_the_approval_route` — A warning deviation does not change the approval route
- `test_a_compliant_draft_passes_cleanly` — A compliant draft passes cleanly
- `test_a_generated_draft_is_compliant_with_the_policy_that_shaped_it` — A generated draft is compliant with the policy that shaped it
- `test_a_rule_naming_an_unknown_clause_is_rejected` — A rule naming an unknown clause is rejected
- `test_unknown_rule_kinds_and_severities_are_rejected` — Unknown rule kinds and severities are rejected
- `test_a_duplicated_rule_is_rejected` — A duplicated rule is rejected
- `test_the_seeded_demo_workspace_is_coherent_end_to_end` — The seeded demo workspace is coherent end to end
- `test_a_drafter_can_choose_a_pre_approved_fallback` — A drafter can choose a pre approved fallback
- `test_no_choice_means_the_preferred_wording` — No choice means the preferred wording
- `test_an_arbitrary_clause_cannot_be_swapped_in` — An arbitrary clause cannot be swapped in
- `test_an_unapproved_alternative_cannot_be_chosen` — An unapproved alternative cannot be chosen
- `test_an_optional_clause_can_be_appended` — An optional clause can be appended
- `test_the_wizard_is_told_the_options_and_their_risk` — The wizard is told the options and their risk
- `test_optional_clauses_exclude_what_the_template_already_uses` — Optional clauses exclude what the template already uses
- `test_a_chosen_fallback_still_satisfies_a_playbook_that_allows_it` — A chosen fallback still satisfies a playbook that allows it

</details>


#### SOW-07

**UAT-SOW-07-01** · Journey 2 review loop until acceptance

*Why it matters:* The RFI's second journey is the one with a loop in it: a reviewer sends it back, the author changes it, and it goes round again until somebody accepts. The loop is the requirement — a workflow that can only go forwards does not model how agreements actually get agreed.

*Automated by:* `test_journeys_e2e.py::test_journey_2_review_loop_until_acceptance` (line 322)

**UAT-SOW-07-02** · Run the redline suite

*Why it matters:* Redline — word-level comparison, accept/reject, anchored threads.

*Automated by:* `test_redline.py` — 22 tests

<details><summary>Tests in this script</summary>

- `test_accepting_everything_reconstructs_the_proposal` — Accepting everything reconstructs the proposal
- `test_accepting_nothing_reconstructs_the_base` — Accepting nothing reconstructs the base
- `test_the_diff_is_deterministic` — The diff is deterministic
- `test_identical_documents_produce_no_changes` — Identical documents produce no changes
- `test_a_changed_cap_shows_the_words_that_moved` — A changed cap shows the words that moved
- `test_each_change_carries_context_so_it_can_be_placed` — Each change carries context so it can be placed
- `test_accepting_one_change_leaves_the_others_alone` — Accepting one change leaves the others alone
- `test_anchors_point_at_the_proposed_wording` — Anchors point at the proposed wording
- `test_word_counts_report_how_much_moved` — Word counts report how much moved
- `test_a_stale_change_index_is_rejected` — A stale change index is rejected
- `test_a_valid_selection_is_normalised` — A valid selection is normalised
- `test_the_summary_reads_as_an_audit_line` — The summary reads as an audit line
- `test_whitespace_only_reformatting_round_trips` — Whitespace only reformatting round trips
- `test_the_default_comparison_is_last_saved_against_the_live_draft` — The default comparison is last saved against the live draft
- `test_comparing_a_version_against_itself_shows_nothing` — Comparing a version against itself shows nothing
- `test_an_unknown_version_is_a_404` — An unknown version is a 404
- `test_applying_a_partial_selection_saves_a_new_version` — Applying a partial selection saves a new version
- `test_applying_a_stale_index_is_refused` — Applying a stale index is refused
- `test_a_signed_agreement_cannot_be_redlined` — A signed agreement cannot be redlined
- `test_a_comment_anchors_to_the_proposed_change` — A comment anchors to the proposed change
- `test_an_inverted_anchor_is_refused` — An inverted anchor is refused
- `test_another_tenant_cannot_see_the_redline` — Another tenant cannot see the redline

</details>


#### SOW-08

**UAT-SOW-08-01** · Run the consolidated review suite

*Why it matters:* Consolidated internal review, @mentions, and the internal-only privacy boundary.

*Automated by:* `test_consolidated_review.py` — 17 tests

<details><summary>Tests in this script</summary>

- `test_internal_comments_are_hidden_from_every_external_audience` — Internal comments are hidden from every external audience
- `test_unknown_audience_is_treated_as_external` — Unknown audience is treated as external
- `test_assert_external_safe_raises_on_a_leak` — Assert external safe raises on a leak
- `test_assert_external_safe_passes_clean_payloads` — Assert external safe passes clean payloads
- `test_consolidated_view_for_an_external_audience_drops_internal` — Consolidated view for an external audience drops internal
- `test_internal_mention_is_flagged_so_it_cannot_leak_via_the_feed` — Internal mention is flagged so it cannot leak via the feed
- `test_comments_are_grouped_by_reviewing_function` — Comments are grouped by reviewing function
- `test_author_department_is_used_when_none_is_given` — Author department is used when none is given
- `test_unassigned_department_is_grouped_not_dropped` — Unassigned department is grouped not dropped
- `test_mention_by_full_name_notifies` — Mention by full name notifies
- `test_mention_by_email_local_part` — Mention by email local part
- `test_self_mention_does_not_notify` — Self mention does not notify
- `test_unresolvable_mention_is_ignored` — Unresolvable mention is ignored
- `test_email_address_in_a_comment_is_not_a_mention` — Email address in a comment is not a mention
- `test_unread_count_and_mark_read` — Unread count and mark read
- `test_only_client_facing_users_may_transmit_externally` — Only client facing users may transmit externally
- `test_admins_retain_the_capability` — Admins retain the capability

</details>

**UAT-SOW-08-02** · Journey 2 review loop until acceptance

*Why it matters:* The RFI's second journey is the one with a loop in it: a reviewer sends it back, the author changes it, and it goes round again until somebody accepts. The loop is the requirement — a workflow that can only go forwards does not model how agreements actually get agreed.

*Automated by:* `test_journeys_e2e.py::test_journey_2_review_loop_until_acceptance` (line 322)


#### SOW-09

**UAT-SOW-09-01** · Run the consolidated review suite

*Why it matters:* Consolidated internal review, @mentions, and the internal-only privacy boundary.

*Automated by:* `test_consolidated_review.py` — 17 tests

<details><summary>Tests in this script</summary>

- `test_internal_comments_are_hidden_from_every_external_audience` — Internal comments are hidden from every external audience
- `test_unknown_audience_is_treated_as_external` — Unknown audience is treated as external
- `test_assert_external_safe_raises_on_a_leak` — Assert external safe raises on a leak
- `test_assert_external_safe_passes_clean_payloads` — Assert external safe passes clean payloads
- `test_consolidated_view_for_an_external_audience_drops_internal` — Consolidated view for an external audience drops internal
- `test_internal_mention_is_flagged_so_it_cannot_leak_via_the_feed` — Internal mention is flagged so it cannot leak via the feed
- `test_comments_are_grouped_by_reviewing_function` — Comments are grouped by reviewing function
- `test_author_department_is_used_when_none_is_given` — Author department is used when none is given
- `test_unassigned_department_is_grouped_not_dropped` — Unassigned department is grouped not dropped
- `test_mention_by_full_name_notifies` — Mention by full name notifies
- `test_mention_by_email_local_part` — Mention by email local part
- `test_self_mention_does_not_notify` — Self mention does not notify
- `test_unresolvable_mention_is_ignored` — Unresolvable mention is ignored
- `test_email_address_in_a_comment_is_not_a_mention` — Email address in a comment is not a mention
- `test_unread_count_and_mark_read` — Unread count and mark read
- `test_only_client_facing_users_may_transmit_externally` — Only client facing users may transmit externally
- `test_admins_retain_the_capability` — Admins retain the capability

</details>


#### SOW-10

**UAT-SOW-10-01** · Run the clause library suite

*Why it matters:* Clause library, alternatives, and the playbook policy engine.

*Automated by:* `test_clause_library.py` — 47 tests

<details><summary>Tests in this script</summary>

- `test_a_draft_clause_has_no_approved_wording` — A draft clause has no approved wording
- `test_submit_then_approve_freezes_a_version` — Submit then approve freezes a version
- `test_the_author_cannot_approve_their_own_clause` — The author cannot approve their own clause
- `test_an_empty_clause_cannot_be_submitted` — An empty clause cannot be submitted
- `test_approving_again_supersedes_the_previous_version` — Approving again supersedes the previous version
- `test_editing_approved_wording_sends_it_back_to_draft` — Editing approved wording sends it back to draft
- `test_retiring_takes_the_clause_and_its_versions_out_of_use` — Retiring takes the clause and its versions out of use
- `test_alternatives_are_ranked_fallbacks_of_their_parent` — Alternatives are ranked fallbacks of their parent
- `test_an_alternative_needs_approval_like_anything_else` — An alternative needs approval like anything else
- `test_references_are_found_in_order_without_duplicates` — References are found in order without duplicates
- `test_expand_inserts_the_approved_wording` — Expand inserts the approved wording
- `test_expand_uses_the_approved_snapshot_not_a_live_edit` — Expand uses the approved snapshot not a live edit
- `test_an_unresolvable_reference_is_reported_not_dropped` — An unresolvable reference is reported not dropped
- `test_an_unapproved_clause_does_not_resolve` — An unapproved clause does not resolve
- `test_validate_references_explains_both_failure_modes` — Validate references explains both failure modes
- `test_a_clause_may_itself_contain_merge_fields` — A clause may itself contain merge fields
- `test_a_template_cannot_be_approved_with_a_broken_reference` — A template cannot be approved with a broken reference
- `test_generation_refuses_when_a_clause_loses_its_approval` — Generation refuses when a clause loses its approval
- `test_a_playbook_only_applies_to_its_contract_type` — A playbook only applies to its contract type
- `test_a_house_wide_playbook_applies_to_everything` — A house wide playbook applies to everything
- `test_both_the_house_policy_and_the_type_policy_apply` — Both the house policy and the type policy apply
- `test_a_value_threshold_narrows_the_policy` — A value threshold narrows the policy
- `test_a_draft_playbook_does_not_apply` — A draft playbook does not apply
- `test_an_unchanged_clause_is_present` — An unchanged clause is present
- `test_formatting_alone_is_not_a_deviation` — Formatting alone is not a deviation
- `test_a_missing_clause_is_reported_as_missing` — A missing clause is reported as missing
- `test_an_edited_cap_is_reported_as_altered_with_a_diff` — An edited cap is reported as altered with a diff
- `test_prohibited_language_is_caught_when_present` — Prohibited language is caught when present
- `test_prohibited_language_that_is_absent_produces_no_finding` — Prohibited language that is absent produces no finding
- `test_the_same_rule_in_two_playbooks_is_one_finding` — The same rule in two playbooks is one finding
- `test_an_unapproved_clause_is_not_measured_against` — An unapproved clause is not measured against
- `test_a_blocking_deviation_classifies_the_agreement_non_standard` — A blocking deviation classifies the agreement non standard
- `test_a_warning_deviation_does_not_change_the_approval_route` — A warning deviation does not change the approval route
- `test_a_compliant_draft_passes_cleanly` — A compliant draft passes cleanly
- `test_a_generated_draft_is_compliant_with_the_policy_that_shaped_it` — A generated draft is compliant with the policy that shaped it
- `test_a_rule_naming_an_unknown_clause_is_rejected` — A rule naming an unknown clause is rejected
- `test_unknown_rule_kinds_and_severities_are_rejected` — Unknown rule kinds and severities are rejected
- `test_a_duplicated_rule_is_rejected` — A duplicated rule is rejected
- `test_the_seeded_demo_workspace_is_coherent_end_to_end` — The seeded demo workspace is coherent end to end
- `test_a_drafter_can_choose_a_pre_approved_fallback` — A drafter can choose a pre approved fallback
- `test_no_choice_means_the_preferred_wording` — No choice means the preferred wording
- `test_an_arbitrary_clause_cannot_be_swapped_in` — An arbitrary clause cannot be swapped in
- `test_an_unapproved_alternative_cannot_be_chosen` — An unapproved alternative cannot be chosen
- `test_an_optional_clause_can_be_appended` — An optional clause can be appended
- `test_the_wizard_is_told_the_options_and_their_risk` — The wizard is told the options and their risk
- `test_optional_clauses_exclude_what_the_template_already_uses` — Optional clauses exclude what the template already uses
- `test_a_chosen_fallback_still_satisfies_a_playbook_that_allows_it` — A chosen fallback still satisfies a playbook that allows it

</details>


#### SOW-11

**UAT-SOW-11-01** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)

**UAT-SOW-11-02** · Journey 2 review loop until acceptance

*Why it matters:* The RFI's second journey is the one with a loop in it: a reviewer sends it back, the author changes it, and it goes round again until somebody accepts. The loop is the requirement — a workflow that can only go forwards does not model how agreements actually get agreed.

*Automated by:* `test_journeys_e2e.py::test_journey_2_review_loop_until_acceptance` (line 322)

**UAT-SOW-11-03** · A rejected agreement does not become signable

*Why it matters:* SOW-11. Rejection is not "changes requested" — it ends the attempt, and an agreement that was rejected must not be sendable by any route.

*Automated by:* `test_journeys_e2e.py::test_a_rejected_agreement_does_not_become_signable` (line 395)

**UAT-SOW-11-04** · Run the readiness suite

*Why it matters:* Sign-off readiness pack.

*Automated by:* `test_readiness.py` — 15 tests

<details><summary>Tests in this script</summary>

- `test_an_agreement_with_no_approval_run_is_not_ready` — An agreement with no approval run is not ready
- `test_a_running_workflow_blocks_and_names_who_it_is_waiting_on` — A running workflow blocks and names who it is waiting on
- `test_a_completed_approval_makes_it_ready` — A completed approval makes it ready
- `test_the_approval_record_names_who_decided_what` — The approval record names who decided what
- `test_a_rejected_workflow_blocks` — A rejected workflow blocks
- `test_a_blocking_policy_deviation_blocks_signature` — A blocking policy deviation blocks signature
- `test_a_warning_deviation_is_a_note_not_a_blocker` — A warning deviation is a note not a blocker
- `test_an_open_amendment_thread_blocks` — An open amendment thread blocks
- `test_a_resolved_amendment_thread_does_not_block` — A resolved amendment thread does not block
- `test_provenance_records_the_template_revision` — Provenance records the template revision
- `test_a_clause_revised_since_generation_is_surfaced` — A clause revised since generation is surfaced
- `test_it_notices_the_body_was_edited_after_generation` — It notices the body was edited after generation
- `test_legal_hold_is_flagged` — Legal hold is flagged
- `test_the_pdf_renders_and_says_whether_it_is_ready` — The PDF renders and says whether it is ready
- `test_the_pdf_renders_for_a_blocked_agreement_too` — The PDF renders for a blocked agreement too

</details>

**UAT-SOW-11-05** · Run the workflow engine suite

*Why it matters:* Workflow engine — parallel stages, completion policies, SLA, escalation, delegation.

*Automated by:* `test_workflow_engine.py` — 39 tests

<details><summary>Tests in this script</summary>

- `test_security_import` — Security import
- `test_every_step_in_a_stage_activates_together` — Every step in a stage activates together
- `test_reviewers_complete_independently_and_out_of_order` — Reviewers complete independently and out of order
- `test_next_stage_activates_only_after_the_current_one_completes` — Next stage activates only after the current one completes
- `test_rejection_ends_the_run_immediately` — Rejection ends the run immediately
- `test_legacy_flat_definition_still_runs_sequentially` — Legacy flat definition still runs sequentially
- `test_any_completes_on_the_first_approval` — Any completes on the first approval
- `test_quorum_needs_the_configured_count` — Quorum needs the configured count
- `test_percentage_rounds_to_a_whole_reviewer` — Percentage rounds to a whole reviewer
- `test_unknown_policy_falls_back_to_all` — Unknown policy falls back to all
- `test_rule_adds_a_stage_when_the_value_crosses_a_threshold` — Rule adds a stage when the value crosses a threshold
- `test_rule_matching_nobody_is_skipped_not_inserted` — Rule matching nobody is skipped not inserted
- `test_non_standard_only_rule_waits_for_the_flag` — Non standard only rule waits for the flag
- `test_material_change_triggers_a_reroute` — Material change triggers a reroute
- `test_immaterial_change_does_not_disturb_a_running_review` — Immaterial change does not disturb a running review
- `test_assignment_routes_to_the_proxy` — Assignment routes to the proxy
- `test_expired_delegation_does_not_route` — Expired delegation does not route
- `test_scoped_delegation_only_covers_its_contract_type` — Scoped delegation only covers its contract type
- `test_both_parties_appear_in_the_decision_audit` — Both parties appear in the decision audit
- `test_reviewer_can_be_added_to_a_running_stage` — Reviewer can be added to a running stage
- `test_adding_a_reviewer_is_audited` — Adding a reviewer is audited
- `test_a_decided_reviewer_cannot_be_removed` — A decided reviewer cannot be removed
- `test_a_stage_must_keep_at_least_one_reviewer` — A stage must keep at least one reviewer
- `test_removing_the_last_outstanding_reviewer_completes_the_stage` — Removing the last outstanding reviewer completes the stage
- `test_only_the_submitter_or_an_admin_can_change_the_set` — Only the submitter or an admin can change the set
- `test_due_date_is_set_on_the_business_calendar` — Due date is set on the business calendar
- `test_reminder_fires_before_the_deadline_and_only_once` — Reminder fires before the deadline and only once
- `test_breach_escalates_once` — Breach escalates once
- `test_escalation_without_a_target_notifies_rather_than_reassigns` — Escalation without a target notifies rather than reassigns
- `test_escalations_feed_is_queryable` — Escalations feed is queryable
- `test_decision_records_whether_it_was_on_time` — Decision records whether it was on time
- `test_steps_without_an_sla_are_untouched` — Steps without an SLA are untouched
- `test_weekend_is_skipped` — Weekend is skipped
- `test_hours_outside_the_working_day_do_not_count` — Hours outside the working day do not count
- `test_elapsed_excludes_the_weekend` — Elapsed excludes the weekend
- `test_holiday_is_not_a_working_day` — Holiday is not a working day
- `test_zero_hours_is_a_no_op` — Zero hours is a no op
- `test_marking_is_idempotent_and_audited` — Marking is idempotent and audited
- `test_non_standard_definition_selects_the_other_route` — Non standard definition selects the other route

</details>


#### SOW-12

**UAT-SOW-12-01** · Run the workflow engine suite

*Why it matters:* Workflow engine — parallel stages, completion policies, SLA, escalation, delegation.

*Automated by:* `test_workflow_engine.py` — 39 tests

<details><summary>Tests in this script</summary>

- `test_security_import` — Security import
- `test_every_step_in_a_stage_activates_together` — Every step in a stage activates together
- `test_reviewers_complete_independently_and_out_of_order` — Reviewers complete independently and out of order
- `test_next_stage_activates_only_after_the_current_one_completes` — Next stage activates only after the current one completes
- `test_rejection_ends_the_run_immediately` — Rejection ends the run immediately
- `test_legacy_flat_definition_still_runs_sequentially` — Legacy flat definition still runs sequentially
- `test_any_completes_on_the_first_approval` — Any completes on the first approval
- `test_quorum_needs_the_configured_count` — Quorum needs the configured count
- `test_percentage_rounds_to_a_whole_reviewer` — Percentage rounds to a whole reviewer
- `test_unknown_policy_falls_back_to_all` — Unknown policy falls back to all
- `test_rule_adds_a_stage_when_the_value_crosses_a_threshold` — Rule adds a stage when the value crosses a threshold
- `test_rule_matching_nobody_is_skipped_not_inserted` — Rule matching nobody is skipped not inserted
- `test_non_standard_only_rule_waits_for_the_flag` — Non standard only rule waits for the flag
- `test_material_change_triggers_a_reroute` — Material change triggers a reroute
- `test_immaterial_change_does_not_disturb_a_running_review` — Immaterial change does not disturb a running review
- `test_assignment_routes_to_the_proxy` — Assignment routes to the proxy
- `test_expired_delegation_does_not_route` — Expired delegation does not route
- `test_scoped_delegation_only_covers_its_contract_type` — Scoped delegation only covers its contract type
- `test_both_parties_appear_in_the_decision_audit` — Both parties appear in the decision audit
- `test_reviewer_can_be_added_to_a_running_stage` — Reviewer can be added to a running stage
- `test_adding_a_reviewer_is_audited` — Adding a reviewer is audited
- `test_a_decided_reviewer_cannot_be_removed` — A decided reviewer cannot be removed
- `test_a_stage_must_keep_at_least_one_reviewer` — A stage must keep at least one reviewer
- `test_removing_the_last_outstanding_reviewer_completes_the_stage` — Removing the last outstanding reviewer completes the stage
- `test_only_the_submitter_or_an_admin_can_change_the_set` — Only the submitter or an admin can change the set
- `test_due_date_is_set_on_the_business_calendar` — Due date is set on the business calendar
- `test_reminder_fires_before_the_deadline_and_only_once` — Reminder fires before the deadline and only once
- `test_breach_escalates_once` — Breach escalates once
- `test_escalation_without_a_target_notifies_rather_than_reassigns` — Escalation without a target notifies rather than reassigns
- `test_escalations_feed_is_queryable` — Escalations feed is queryable
- `test_decision_records_whether_it_was_on_time` — Decision records whether it was on time
- `test_steps_without_an_sla_are_untouched` — Steps without an SLA are untouched
- `test_weekend_is_skipped` — Weekend is skipped
- `test_hours_outside_the_working_day_do_not_count` — Hours outside the working day do not count
- `test_elapsed_excludes_the_weekend` — Elapsed excludes the weekend
- `test_holiday_is_not_a_working_day` — Holiday is not a working day
- `test_zero_hours_is_a_no_op` — Zero hours is a no op
- `test_marking_is_idempotent_and_audited` — Marking is idempotent and audited
- `test_non_standard_definition_selects_the_other_route` — Non standard definition selects the other route

</details>


#### SOW-13

> **Also requires manual acceptance.** The approval matrix must match MMBL's actual delegation policy, which no test can know.

**UAT-SOW-13-01** · Run the workflow engine suite

*Why it matters:* Workflow engine — parallel stages, completion policies, SLA, escalation, delegation.

*Automated by:* `test_workflow_engine.py` — 39 tests

<details><summary>Tests in this script</summary>

- `test_security_import` — Security import
- `test_every_step_in_a_stage_activates_together` — Every step in a stage activates together
- `test_reviewers_complete_independently_and_out_of_order` — Reviewers complete independently and out of order
- `test_next_stage_activates_only_after_the_current_one_completes` — Next stage activates only after the current one completes
- `test_rejection_ends_the_run_immediately` — Rejection ends the run immediately
- `test_legacy_flat_definition_still_runs_sequentially` — Legacy flat definition still runs sequentially
- `test_any_completes_on_the_first_approval` — Any completes on the first approval
- `test_quorum_needs_the_configured_count` — Quorum needs the configured count
- `test_percentage_rounds_to_a_whole_reviewer` — Percentage rounds to a whole reviewer
- `test_unknown_policy_falls_back_to_all` — Unknown policy falls back to all
- `test_rule_adds_a_stage_when_the_value_crosses_a_threshold` — Rule adds a stage when the value crosses a threshold
- `test_rule_matching_nobody_is_skipped_not_inserted` — Rule matching nobody is skipped not inserted
- `test_non_standard_only_rule_waits_for_the_flag` — Non standard only rule waits for the flag
- `test_material_change_triggers_a_reroute` — Material change triggers a reroute
- `test_immaterial_change_does_not_disturb_a_running_review` — Immaterial change does not disturb a running review
- `test_assignment_routes_to_the_proxy` — Assignment routes to the proxy
- `test_expired_delegation_does_not_route` — Expired delegation does not route
- `test_scoped_delegation_only_covers_its_contract_type` — Scoped delegation only covers its contract type
- `test_both_parties_appear_in_the_decision_audit` — Both parties appear in the decision audit
- `test_reviewer_can_be_added_to_a_running_stage` — Reviewer can be added to a running stage
- `test_adding_a_reviewer_is_audited` — Adding a reviewer is audited
- `test_a_decided_reviewer_cannot_be_removed` — A decided reviewer cannot be removed
- `test_a_stage_must_keep_at_least_one_reviewer` — A stage must keep at least one reviewer
- `test_removing_the_last_outstanding_reviewer_completes_the_stage` — Removing the last outstanding reviewer completes the stage
- `test_only_the_submitter_or_an_admin_can_change_the_set` — Only the submitter or an admin can change the set
- `test_due_date_is_set_on_the_business_calendar` — Due date is set on the business calendar
- `test_reminder_fires_before_the_deadline_and_only_once` — Reminder fires before the deadline and only once
- `test_breach_escalates_once` — Breach escalates once
- `test_escalation_without_a_target_notifies_rather_than_reassigns` — Escalation without a target notifies rather than reassigns
- `test_escalations_feed_is_queryable` — Escalations feed is queryable
- `test_decision_records_whether_it_was_on_time` — Decision records whether it was on time
- `test_steps_without_an_sla_are_untouched` — Steps without an SLA are untouched
- `test_weekend_is_skipped` — Weekend is skipped
- `test_hours_outside_the_working_day_do_not_count` — Hours outside the working day do not count
- `test_elapsed_excludes_the_weekend` — Elapsed excludes the weekend
- `test_holiday_is_not_a_working_day` — Holiday is not a working day
- `test_zero_hours_is_a_no_op` — Zero hours is a no op
- `test_marking_is_idempotent_and_audited` — Marking is idempotent and audited
- `test_non_standard_definition_selects_the_other_route` — Non standard definition selects the other route

</details>


#### SOW-14

**UAT-SOW-14-01** · Run the workflow engine suite

*Why it matters:* Workflow engine — parallel stages, completion policies, SLA, escalation, delegation.

*Automated by:* `test_workflow_engine.py` — 39 tests

<details><summary>Tests in this script</summary>

- `test_security_import` — Security import
- `test_every_step_in_a_stage_activates_together` — Every step in a stage activates together
- `test_reviewers_complete_independently_and_out_of_order` — Reviewers complete independently and out of order
- `test_next_stage_activates_only_after_the_current_one_completes` — Next stage activates only after the current one completes
- `test_rejection_ends_the_run_immediately` — Rejection ends the run immediately
- `test_legacy_flat_definition_still_runs_sequentially` — Legacy flat definition still runs sequentially
- `test_any_completes_on_the_first_approval` — Any completes on the first approval
- `test_quorum_needs_the_configured_count` — Quorum needs the configured count
- `test_percentage_rounds_to_a_whole_reviewer` — Percentage rounds to a whole reviewer
- `test_unknown_policy_falls_back_to_all` — Unknown policy falls back to all
- `test_rule_adds_a_stage_when_the_value_crosses_a_threshold` — Rule adds a stage when the value crosses a threshold
- `test_rule_matching_nobody_is_skipped_not_inserted` — Rule matching nobody is skipped not inserted
- `test_non_standard_only_rule_waits_for_the_flag` — Non standard only rule waits for the flag
- `test_material_change_triggers_a_reroute` — Material change triggers a reroute
- `test_immaterial_change_does_not_disturb_a_running_review` — Immaterial change does not disturb a running review
- `test_assignment_routes_to_the_proxy` — Assignment routes to the proxy
- `test_expired_delegation_does_not_route` — Expired delegation does not route
- `test_scoped_delegation_only_covers_its_contract_type` — Scoped delegation only covers its contract type
- `test_both_parties_appear_in_the_decision_audit` — Both parties appear in the decision audit
- `test_reviewer_can_be_added_to_a_running_stage` — Reviewer can be added to a running stage
- `test_adding_a_reviewer_is_audited` — Adding a reviewer is audited
- `test_a_decided_reviewer_cannot_be_removed` — A decided reviewer cannot be removed
- `test_a_stage_must_keep_at_least_one_reviewer` — A stage must keep at least one reviewer
- `test_removing_the_last_outstanding_reviewer_completes_the_stage` — Removing the last outstanding reviewer completes the stage
- `test_only_the_submitter_or_an_admin_can_change_the_set` — Only the submitter or an admin can change the set
- `test_due_date_is_set_on_the_business_calendar` — Due date is set on the business calendar
- `test_reminder_fires_before_the_deadline_and_only_once` — Reminder fires before the deadline and only once
- `test_breach_escalates_once` — Breach escalates once
- `test_escalation_without_a_target_notifies_rather_than_reassigns` — Escalation without a target notifies rather than reassigns
- `test_escalations_feed_is_queryable` — Escalations feed is queryable
- `test_decision_records_whether_it_was_on_time` — Decision records whether it was on time
- `test_steps_without_an_sla_are_untouched` — Steps without an SLA are untouched
- `test_weekend_is_skipped` — Weekend is skipped
- `test_hours_outside_the_working_day_do_not_count` — Hours outside the working day do not count
- `test_elapsed_excludes_the_weekend` — Elapsed excludes the weekend
- `test_holiday_is_not_a_working_day` — Holiday is not a working day
- `test_zero_hours_is_a_no_op` — Zero hours is a no op
- `test_marking_is_idempotent_and_audited` — Marking is idempotent and audited
- `test_non_standard_definition_selects_the_other_route` — Non standard definition selects the other route

</details>


#### SOW-15

**UAT-SOW-15-01** · Journey 2 review loop until acceptance

*Why it matters:* The RFI's second journey is the one with a loop in it: a reviewer sends it back, the author changes it, and it goes round again until somebody accepts. The loop is the requirement — a workflow that can only go forwards does not model how agreements actually get agreed.

*Automated by:* `test_journeys_e2e.py::test_journey_2_review_loop_until_acceptance` (line 322)

**UAT-SOW-15-02** · Run the workflow engine suite

*Why it matters:* Workflow engine — parallel stages, completion policies, SLA, escalation, delegation.

*Automated by:* `test_workflow_engine.py` — 39 tests

<details><summary>Tests in this script</summary>

- `test_security_import` — Security import
- `test_every_step_in_a_stage_activates_together` — Every step in a stage activates together
- `test_reviewers_complete_independently_and_out_of_order` — Reviewers complete independently and out of order
- `test_next_stage_activates_only_after_the_current_one_completes` — Next stage activates only after the current one completes
- `test_rejection_ends_the_run_immediately` — Rejection ends the run immediately
- `test_legacy_flat_definition_still_runs_sequentially` — Legacy flat definition still runs sequentially
- `test_any_completes_on_the_first_approval` — Any completes on the first approval
- `test_quorum_needs_the_configured_count` — Quorum needs the configured count
- `test_percentage_rounds_to_a_whole_reviewer` — Percentage rounds to a whole reviewer
- `test_unknown_policy_falls_back_to_all` — Unknown policy falls back to all
- `test_rule_adds_a_stage_when_the_value_crosses_a_threshold` — Rule adds a stage when the value crosses a threshold
- `test_rule_matching_nobody_is_skipped_not_inserted` — Rule matching nobody is skipped not inserted
- `test_non_standard_only_rule_waits_for_the_flag` — Non standard only rule waits for the flag
- `test_material_change_triggers_a_reroute` — Material change triggers a reroute
- `test_immaterial_change_does_not_disturb_a_running_review` — Immaterial change does not disturb a running review
- `test_assignment_routes_to_the_proxy` — Assignment routes to the proxy
- `test_expired_delegation_does_not_route` — Expired delegation does not route
- `test_scoped_delegation_only_covers_its_contract_type` — Scoped delegation only covers its contract type
- `test_both_parties_appear_in_the_decision_audit` — Both parties appear in the decision audit
- `test_reviewer_can_be_added_to_a_running_stage` — Reviewer can be added to a running stage
- `test_adding_a_reviewer_is_audited` — Adding a reviewer is audited
- `test_a_decided_reviewer_cannot_be_removed` — A decided reviewer cannot be removed
- `test_a_stage_must_keep_at_least_one_reviewer` — A stage must keep at least one reviewer
- `test_removing_the_last_outstanding_reviewer_completes_the_stage` — Removing the last outstanding reviewer completes the stage
- `test_only_the_submitter_or_an_admin_can_change_the_set` — Only the submitter or an admin can change the set
- `test_due_date_is_set_on_the_business_calendar` — Due date is set on the business calendar
- `test_reminder_fires_before_the_deadline_and_only_once` — Reminder fires before the deadline and only once
- `test_breach_escalates_once` — Breach escalates once
- `test_escalation_without_a_target_notifies_rather_than_reassigns` — Escalation without a target notifies rather than reassigns
- `test_escalations_feed_is_queryable` — Escalations feed is queryable
- `test_decision_records_whether_it_was_on_time` — Decision records whether it was on time
- `test_steps_without_an_sla_are_untouched` — Steps without an SLA are untouched
- `test_weekend_is_skipped` — Weekend is skipped
- `test_hours_outside_the_working_day_do_not_count` — Hours outside the working day do not count
- `test_elapsed_excludes_the_weekend` — Elapsed excludes the weekend
- `test_holiday_is_not_a_working_day` — Holiday is not a working day
- `test_zero_hours_is_a_no_op` — Zero hours is a no op
- `test_marking_is_idempotent_and_audited` — Marking is idempotent and audited
- `test_non_standard_definition_selects_the_other_route` — Non standard definition selects the other route

</details>


#### SOW-16

**UAT-SOW-16-01** · Run the access control suite

*Why it matters:* Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

*Automated by:* `test_access_control.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_builtin_roles_carry_what_they_should` — The builtin roles carry what they should
- `test_an_unknown_role_degrades_to_viewer_not_to_nothing` — An unknown role degrades to viewer not to nothing
- `test_a_custom_role_extends_its_base` — A custom role extends its base
- `test_a_revoke_always_wins` — A revoke always wins
- `test_an_inactive_custom_role_falls_back` — An inactive custom role falls back
- `test_require_raises_rather_than_returning_false` — Require raises rather than returning false
- `test_the_author_of_an_agreement_cannot_approve_it` — The author of an agreement cannot approve it
- `test_somebody_else_can_approve_it` — Somebody else can approve it
- `test_the_rule_is_per_object_not_global` — The rule is per object not global
- `test_a_block_is_recorded` — A block is recorded
- `test_an_override_needs_a_reason_and_is_audited_loudly` — An override needs a reason and is audited loudly
- `test_a_webhook_creator_cannot_reveal_its_own_secret` — A webhook creator cannot reveal its own secret
- `test_an_unrelated_action_is_not_segregated` — An unrelated action is not segregated
- `test_only_sensitive_actions_need_step_up` — Only sensitive actions need step up
- `test_a_sensitive_action_without_a_challenge_demands_one` — A sensitive action without a challenge demands one
- `test_a_satisfied_challenge_lets_the_action_through` — A satisfied challenge lets the action through
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_a_challenge_cannot_be_replayed_against_another_object` — A challenge cannot be replayed against another object
- `test_a_challenge_cannot_be_reused_for_a_different_action` — A challenge cannot be reused for a different action
- `test_a_wrong_password_does_not_satisfy_a_challenge` — A wrong password does not satisfy a challenge
- `test_repeated_wrong_answers_burn_the_challenge` — Repeated wrong answers burn the challenge
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_somebody_elses_challenge_cannot_be_answered` — Somebody elses challenge cannot be answered
- `test_an_ordinary_agreement_is_visible_to_everyone` — An ordinary agreement is visible to everyone
- `test_a_confidential_agreement_is_not` — A confidential agreement is not
- `test_the_owner_can_always_see_their_own` — The owner can always see their own
- `test_an_explicit_grant_opens_it` — An explicit grant opens it
- `test_a_role_grant_opens_it_for_that_role` — A role grant opens it for that role
- `test_an_expired_grant_closes_again` — An expired grant closes again
- `test_a_refused_read_is_logged` — A refused read is logged
- `test_break_glass_needs_a_reason` — Break glass needs a reason
- `test_break_glass_grants_access_and_shouts_about_it` — Break glass grants access and shouts about it
- `test_a_link_resolves_to_its_record` — A link resolves to its record
- `test_only_the_hash_is_stored` — Only the hash is stored
- `test_a_revoked_link_stops_resolving` — A revoked link stops resolving
- `test_an_expired_link_stops_resolving` — An expired link stops resolving
- `test_a_wrong_token_resolves_to_nothing` — A wrong token resolves to nothing
- `test_an_absurd_duration_is_refused` — An absurd duration is refused
- `test_the_expiry_sweep_is_idempotent` — The expiry sweep is idempotent
- `test_placing_a_hold_sets_the_flag_every_retention_path_reads` — Placing a hold sets the flag every retention path reads
- `test_a_hold_needs_a_matter_and_something_to_hold` — A hold needs a matter and something to hold
- `test_a_hold_over_a_missing_agreement_is_refused` — A hold over a missing agreement is refused
- `test_releasing_needs_a_reason` — Releasing needs a reason
- `test_releasing_the_only_hold_clears_the_flag` — Releasing the only hold clears the flag
- `test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers` — Releasing one matter does not expose an agreement another still covers
- `test_a_released_hold_cannot_be_released_twice` — A released hold cannot be released twice
- `test_extending_a_hold_covers_the_new_agreements` — Extending a hold covers the new agreements
- `test_the_export_set_carries_audit_chain_positions` — The export set carries audit chain positions
- `test_reconcile_repairs_a_drifted_flag` — Reconcile repairs a drifted flag

</details>


#### SOW-17

**UAT-SOW-17-01** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)

**UAT-SOW-17-02** · Run the signing engine suite

*Why it matters:* The e-signature engine (Phase 10 — coverage on `signing_service`).

*Automated by:* `test_signing_engine.py` — 44 tests

<details><summary>Tests in this script</summary>

- `test_an_envelope_needs_a_signer` — An envelope needs a signer
- `test_recipients_keep_the_order_they_were_given` — Recipients keep the order they were given
- `test_an_internal_signer_is_bound_to_their_workspace_identity` — An internal signer is bound to their workspace identity
- `test_a_user_in_another_tenant_is_not_matched` — A user in another tenant is not matched
- `test_an_unsent_envelope_has_no_tokens` — An unsent envelope has no tokens
- `test_sending_snapshots_what_is_being_signed` — Sending snapshots what is being signed
- `test_sending_twice_is_refused` — Sending twice is refused
- `test_sequential_sending_invites_only_the_first_signer` — Sequential sending invites only the first signer
- `test_parallel_sending_invites_everybody_at_once` — Parallel sending invites everybody at once
- `test_cc_recipients_are_notified_immediately_in_either_order` — CC recipients are notified immediately in either order
- `test_a_cc_is_never_anybodys_turn` — A CC is never anybodys turn
- `test_in_parallel_mode_it_is_always_everybodys_turn` — In parallel mode it is always everybodys turn
- `test_signing_out_of_turn_is_refused` — Signing out of turn is refused
- `test_a_sequential_signature_invites_the_next_person` — A sequential signature invites the next person
- `test_the_last_signature_completes_the_envelope` — The last signature completes the envelope
- `test_signing_twice_is_refused` — Signing twice is refused
- `test_a_cc_cannot_sign` — A CC cannot sign
- `test_a_completed_envelope_cannot_be_signed_again` — A completed envelope cannot be signed again
- `test_a_stale_envelope_read_cannot_overwrite_a_fresh_signature` — A stale envelope read cannot overwrite a fresh signature
- `test_the_lock_version_advances_on_every_claim` — The lock version advances on every claim
- `test_a_real_png_is_accepted` — A real png is accepted
- `test_a_bad_signature_image_is_rejected` — A bad signature image is rejected
- `test_an_oversized_image_is_rejected` — An oversized image is rejected
- `test_a_drawn_signature_without_an_image_is_refused` — A drawn signature without an image is refused
- `test_a_drawn_signature_is_stored` — A drawn signature is stored
- `test_an_unknown_signature_kind_falls_back_to_typed` — An unknown signature kind falls back to typed
- `test_signature_initials_and_date_tabs_fill_themselves` — Signature initials and date tabs fill themselves
- `test_a_required_text_tab_blocks_signing_until_filled` — A required text tab blocks signing until filled
- `test_a_filled_required_tab_lets_signing_through` — A filled required tab lets signing through
- `test_a_checkbox_tab_reads_the_usual_truthy_spellings` — A checkbox tab reads the usual truthy spellings
- `test_a_recipient_with_no_tabs_is_not_blocked` — A recipient with no tabs is not blocked
- `test_initials_of_a_single_word_name` — Initials of a single word name
- `test_declining_ends_the_envelope_for_everyone` — Declining ends the envelope for everyone
- `test_declining_twice_is_refused` — Declining twice is refused
- `test_somebody_who_signed_cannot_then_decline` — Somebody who signed cannot then decline
- `test_voiding_kills_every_link` — Voiding kills every link
- `test_a_completed_envelope_cannot_be_voided` — A completed envelope cannot be voided
- `test_reminding_somebody_who_has_signed_is_refused` — Reminding somebody who has signed is refused
- `test_a_reminder_is_recorded` — A reminder is recorded
- `test_opening_the_link_is_recorded_once` — Opening the link is recorded once
- `test_the_current_envelope_is_the_newest_one` — The current envelope is the newest one
- `test_the_current_envelope_is_stable_when_timestamps_tie` — The current envelope is stable when timestamps tie
- `test_the_active_envelope_ignores_terminal_ones` — The active envelope ignores terminal ones
- `test_deleting_a_contracts_envelopes_takes_the_whole_tree` — Deleting a contracts envelopes takes the whole tree

</details>


#### SOW-18

**UAT-SOW-18-01** · Run the signing engine suite

*Why it matters:* The e-signature engine (Phase 10 — coverage on `signing_service`).

*Automated by:* `test_signing_engine.py` — 44 tests

<details><summary>Tests in this script</summary>

- `test_an_envelope_needs_a_signer` — An envelope needs a signer
- `test_recipients_keep_the_order_they_were_given` — Recipients keep the order they were given
- `test_an_internal_signer_is_bound_to_their_workspace_identity` — An internal signer is bound to their workspace identity
- `test_a_user_in_another_tenant_is_not_matched` — A user in another tenant is not matched
- `test_an_unsent_envelope_has_no_tokens` — An unsent envelope has no tokens
- `test_sending_snapshots_what_is_being_signed` — Sending snapshots what is being signed
- `test_sending_twice_is_refused` — Sending twice is refused
- `test_sequential_sending_invites_only_the_first_signer` — Sequential sending invites only the first signer
- `test_parallel_sending_invites_everybody_at_once` — Parallel sending invites everybody at once
- `test_cc_recipients_are_notified_immediately_in_either_order` — CC recipients are notified immediately in either order
- `test_a_cc_is_never_anybodys_turn` — A CC is never anybodys turn
- `test_in_parallel_mode_it_is_always_everybodys_turn` — In parallel mode it is always everybodys turn
- `test_signing_out_of_turn_is_refused` — Signing out of turn is refused
- `test_a_sequential_signature_invites_the_next_person` — A sequential signature invites the next person
- `test_the_last_signature_completes_the_envelope` — The last signature completes the envelope
- `test_signing_twice_is_refused` — Signing twice is refused
- `test_a_cc_cannot_sign` — A CC cannot sign
- `test_a_completed_envelope_cannot_be_signed_again` — A completed envelope cannot be signed again
- `test_a_stale_envelope_read_cannot_overwrite_a_fresh_signature` — A stale envelope read cannot overwrite a fresh signature
- `test_the_lock_version_advances_on_every_claim` — The lock version advances on every claim
- `test_a_real_png_is_accepted` — A real png is accepted
- `test_a_bad_signature_image_is_rejected` — A bad signature image is rejected
- `test_an_oversized_image_is_rejected` — An oversized image is rejected
- `test_a_drawn_signature_without_an_image_is_refused` — A drawn signature without an image is refused
- `test_a_drawn_signature_is_stored` — A drawn signature is stored
- `test_an_unknown_signature_kind_falls_back_to_typed` — An unknown signature kind falls back to typed
- `test_signature_initials_and_date_tabs_fill_themselves` — Signature initials and date tabs fill themselves
- `test_a_required_text_tab_blocks_signing_until_filled` — A required text tab blocks signing until filled
- `test_a_filled_required_tab_lets_signing_through` — A filled required tab lets signing through
- `test_a_checkbox_tab_reads_the_usual_truthy_spellings` — A checkbox tab reads the usual truthy spellings
- `test_a_recipient_with_no_tabs_is_not_blocked` — A recipient with no tabs is not blocked
- `test_initials_of_a_single_word_name` — Initials of a single word name
- `test_declining_ends_the_envelope_for_everyone` — Declining ends the envelope for everyone
- `test_declining_twice_is_refused` — Declining twice is refused
- `test_somebody_who_signed_cannot_then_decline` — Somebody who signed cannot then decline
- `test_voiding_kills_every_link` — Voiding kills every link
- `test_a_completed_envelope_cannot_be_voided` — A completed envelope cannot be voided
- `test_reminding_somebody_who_has_signed_is_refused` — Reminding somebody who has signed is refused
- `test_a_reminder_is_recorded` — A reminder is recorded
- `test_opening_the_link_is_recorded_once` — Opening the link is recorded once
- `test_the_current_envelope_is_the_newest_one` — The current envelope is the newest one
- `test_the_current_envelope_is_stable_when_timestamps_tie` — The current envelope is stable when timestamps tie
- `test_the_active_envelope_ignores_terminal_ones` — The active envelope ignores terminal ones
- `test_deleting_a_contracts_envelopes_takes_the_whole_tree` — Deleting a contracts envelopes takes the whole tree

</details>


#### SOW-19

**UAT-SOW-19-01** · Run the signing engine suite

*Why it matters:* The e-signature engine (Phase 10 — coverage on `signing_service`).

*Automated by:* `test_signing_engine.py` — 44 tests

<details><summary>Tests in this script</summary>

- `test_an_envelope_needs_a_signer` — An envelope needs a signer
- `test_recipients_keep_the_order_they_were_given` — Recipients keep the order they were given
- `test_an_internal_signer_is_bound_to_their_workspace_identity` — An internal signer is bound to their workspace identity
- `test_a_user_in_another_tenant_is_not_matched` — A user in another tenant is not matched
- `test_an_unsent_envelope_has_no_tokens` — An unsent envelope has no tokens
- `test_sending_snapshots_what_is_being_signed` — Sending snapshots what is being signed
- `test_sending_twice_is_refused` — Sending twice is refused
- `test_sequential_sending_invites_only_the_first_signer` — Sequential sending invites only the first signer
- `test_parallel_sending_invites_everybody_at_once` — Parallel sending invites everybody at once
- `test_cc_recipients_are_notified_immediately_in_either_order` — CC recipients are notified immediately in either order
- `test_a_cc_is_never_anybodys_turn` — A CC is never anybodys turn
- `test_in_parallel_mode_it_is_always_everybodys_turn` — In parallel mode it is always everybodys turn
- `test_signing_out_of_turn_is_refused` — Signing out of turn is refused
- `test_a_sequential_signature_invites_the_next_person` — A sequential signature invites the next person
- `test_the_last_signature_completes_the_envelope` — The last signature completes the envelope
- `test_signing_twice_is_refused` — Signing twice is refused
- `test_a_cc_cannot_sign` — A CC cannot sign
- `test_a_completed_envelope_cannot_be_signed_again` — A completed envelope cannot be signed again
- `test_a_stale_envelope_read_cannot_overwrite_a_fresh_signature` — A stale envelope read cannot overwrite a fresh signature
- `test_the_lock_version_advances_on_every_claim` — The lock version advances on every claim
- `test_a_real_png_is_accepted` — A real png is accepted
- `test_a_bad_signature_image_is_rejected` — A bad signature image is rejected
- `test_an_oversized_image_is_rejected` — An oversized image is rejected
- `test_a_drawn_signature_without_an_image_is_refused` — A drawn signature without an image is refused
- `test_a_drawn_signature_is_stored` — A drawn signature is stored
- `test_an_unknown_signature_kind_falls_back_to_typed` — An unknown signature kind falls back to typed
- `test_signature_initials_and_date_tabs_fill_themselves` — Signature initials and date tabs fill themselves
- `test_a_required_text_tab_blocks_signing_until_filled` — A required text tab blocks signing until filled
- `test_a_filled_required_tab_lets_signing_through` — A filled required tab lets signing through
- `test_a_checkbox_tab_reads_the_usual_truthy_spellings` — A checkbox tab reads the usual truthy spellings
- `test_a_recipient_with_no_tabs_is_not_blocked` — A recipient with no tabs is not blocked
- `test_initials_of_a_single_word_name` — Initials of a single word name
- `test_declining_ends_the_envelope_for_everyone` — Declining ends the envelope for everyone
- `test_declining_twice_is_refused` — Declining twice is refused
- `test_somebody_who_signed_cannot_then_decline` — Somebody who signed cannot then decline
- `test_voiding_kills_every_link` — Voiding kills every link
- `test_a_completed_envelope_cannot_be_voided` — A completed envelope cannot be voided
- `test_reminding_somebody_who_has_signed_is_refused` — Reminding somebody who has signed is refused
- `test_a_reminder_is_recorded` — A reminder is recorded
- `test_opening_the_link_is_recorded_once` — Opening the link is recorded once
- `test_the_current_envelope_is_the_newest_one` — The current envelope is the newest one
- `test_the_current_envelope_is_stable_when_timestamps_tie` — The current envelope is stable when timestamps tie
- `test_the_active_envelope_ignores_terminal_ones` — The active envelope ignores terminal ones
- `test_deleting_a_contracts_envelopes_takes_the_whole_tree` — Deleting a contracts envelopes takes the whole tree

</details>


#### SOW-21

**UAT-SOW-21-01** · Run the esignature depth suite

*Why it matters:* Phase 2 — per-signatory PAdES signing, the authority matrix, and execution reliability.

*Automated by:* `test_esignature_depth.py` — 18 tests

<details><summary>Tests in this script</summary>

- `test_each_signatory_signs_with_their_own_certificate` — Each signatory signs with their own certificate
- `test_signature_detects_tampering` — Signature detects tampering
- `test_ltv_material_is_embedded` — Ltv material is embedded
- `test_provider_reports_per_signatory_capability` — Provider reports per signatory capability
- `test_one_failure_does_not_lose_the_other_signatures` — One failure does not lose the other signatures
- `test_receipts_name_the_certificate_serial` — Receipts name the certificate serial
- `test_silent_matrix_permits_anything` — Silent matrix permits anything
- `test_value_band_selects_the_rule` — Value band selects the rule
- `test_role_hierarchy_satisfies_a_lower_requirement` — Role hierarchy satisfies a lower requirement
- `test_unauthorised_signatory_is_flagged` — Unauthorised signatory is flagged
- `test_joint_signature_requirement` — Joint signature requirement
- `test_override_needs_a_reason_and_is_audited` — Override needs a reason and is audited
- `test_most_specific_rule_wins` — Most specific rule wins
- `test_rule_changes_are_audited` — Rule changes are audited
- `test_same_user_can_review_and_sign` — Same user can review and sign
- `test_external_counterparty_has_no_internal_binding` — External counterparty has no internal binding
- `test_concurrent_signing_is_rejected_not_silently_merged` — Concurrent signing is rejected not silently merged
- `test_seal_status_defaults_to_pending` — Seal status defaults to pending

</details>

**UAT-SOW-21-02** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)


#### SOW-22

**UAT-SOW-22-01** · Run the visitor esign suite

*Why it matters:* Visitor eSigning — the public, unauthenticated surface.

*Automated by:* `test_visitor_esign.py` — 40 tests

<details><summary>Tests in this script</summary>

- `test_security_module_import_is_not_needed` — Security module import is not needed
- `test_only_a_hash_of_the_token_is_stored` — Only a hash of the token is stored
- `test_token_copy_is_encrypted_at_rest` — Token copy is encrypted at rest
- `test_token_resolves` — Token resolves
- `test_wrong_token_does_not_resolve` — Wrong token does not resolve
- `test_expired_invitation_does_not_resolve` — Expired invitation does not resolve
- `test_revoked_invitation_does_not_resolve` — Revoked invitation does not resolve
- `test_use_cap_closes_the_link` — Use cap closes the link
- `test_start_sends_a_masked_code_and_creates_nothing_irreversible` — Start sends a masked code and creates nothing irreversible
- `test_wrong_code_is_rejected` — Wrong code is rejected
- `test_brute_force_is_blocked` — Brute force is blocked
- `test_expired_code_is_rejected` — Expired code is rejected
- `test_correct_code_verifies_and_burns_the_code` — Correct code verifies and burns the code
- `test_resend_is_capped` — Resend is capped
- `test_session_from_another_invitation_is_not_accepted` — Session from another invitation is not accepted
- `test_sms_channel_requires_a_number` — Sms channel requires a number
- `test_cnic_is_reduced_to_the_last_four_digits` — CNIC is reduced to the last four digits
- `test_rate_limited_per_ip` — Rate limited per ip
- `test_same_identifier_yields_the_same_party` — Same identifier yields the same party
- `test_party_ref_does_not_contain_the_identifier` — Party ref does not contain the identifier
- `test_phone_spellings_normalise_to_one_party` — Phone spellings normalise to one party
- `test_normalisation` — Normalisation
- `test_masking_keeps_only_the_last_four` — Masking keeps only the last four
- `test_signing_is_locked_until_the_document_is_read` — Signing is locked until the document is read
- `test_unverified_session_can_never_sign` — Unverified session can never sign
- `test_evidence_bundle_is_masked` — Evidence bundle is masked
- `test_verified_visitor_gets_their_own_short_lived_certificate` — Verified visitor gets their own short lived certificate
- `test_certificate_records_that_it_was_auto_approved` — Certificate records that it was auto approved
- `test_returning_visitor_reuses_their_certificate` — Returning visitor reuses their certificate
- `test_unverified_session_cannot_get_a_certificate` — Unverified session cannot get a certificate
- `test_missing_pki_does_not_block_signing` — Missing PKI does not block signing
- `test_valid_solution_is_accepted` — Valid solution is accepted
- `test_wrong_solution_is_rejected` — Wrong solution is rejected
- `test_forged_challenge_is_rejected` — Forged challenge is rejected
- `test_challenge_is_bound_to_the_invitation` — Challenge is bound to the invitation
- `test_disabled_when_bits_is_zero` — Disabled when bits is zero
- `test_verified_visitor_joins_the_live_envelope` — Verified visitor joins the live envelope
- `test_no_open_envelope_is_a_clear_error` — No open envelope is a clear error
- `test_reattaching_returns_the_same_recipient` — Reattaching returns the same recipient
- `test_sms_rows_are_marked_and_excluded_from_the_smtp_flush` — Sms rows are marked and excluded from the smtp flush

</details>


#### SOW-23

**UAT-SOW-23-01** · Run the wet signature suite

*Why it matters:* Hybrid execution — some parties sign electronically, some on paper.

*Automated by:* `test_wet_signature.py` — 23 tests

<details><summary>Tests in this script</summary>

- `test_security_import_is_available` — Security import is available
- `test_marking_one_party_makes_the_envelope_hybrid` — Marking one party makes the envelope hybrid
- `test_marking_every_party_makes_it_wet` — Marking every party makes it wet
- `test_clearing_returns_to_electronic` — Clearing returns to electronic
- `test_cannot_switch_someone_who_already_signed` — Cannot switch someone who already signed
- `test_unknown_recipient_is_rejected` — Unknown recipient is rejected
- `test_completed_envelope_is_settled` — Completed envelope is settled
- `test_mode_change_is_audited` — Mode change is audited
- `test_pack_is_a_pdf_naming_the_paper_signatories` — Pack is a PDF naming the paper signatories
- `test_pack_survives_a_missing_document` — Pack survives a missing document
- `test_attesting_advances_the_paper_signatory` — Attesting advances the paper signatory
- `test_evidence_records_the_file_hash_and_the_accountable_person` — Evidence records the file hash and the accountable person
- `test_declared_execution_date_is_not_the_upload_date` — Declared execution date is not the upload date
- `test_attestation_is_audited` — Attestation is audited
- `test_cannot_attest_for_an_electronic_signer` — Cannot attest for an electronic signer
- `test_cannot_attest_on_an_electronic_envelope` — Cannot attest on an electronic envelope
- `test_double_attestation_is_refused` — Double attestation is refused
- `test_one_scan_can_cover_every_paper_signatory` — One scan can cover every paper signatory
- `test_hybrid_envelope_completes_once_both_paths_finish` — Hybrid envelope completes once both paths finish
- `test_completion_emits_the_same_event_as_the_electronic_path` — Completion emits the same event as the electronic path
- `test_summary_separates_scanned_from_cryptographic` — Summary separates scanned from cryptographic
- `test_electronic_only_envelope_carries_no_wet_note` — Electronic only envelope carries no wet note
- `test_wet_signer_gets_no_certificate_binding` — Wet signer gets no certificate binding

</details>


#### SOW-24

**UAT-SOW-24-01** · Run the repository suite

*Why it matters:* Repository structure: parties, relationships, departments, folders, custom fields, search.

*Automated by:* `test_repository.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_same_company_spelled_differently_normalises_the_same` — The same company spelled differently normalises the same
- `test_different_companies_do_not_normalise_together` — Different companies do not normalise together
- `test_normalisation_does_not_eat_a_name_that_is_only_a_suffix` — Normalisation does not eat a name that is only a suffix
- `test_onboarding_blocks_on_a_near_identical_name` — Onboarding blocks on a near identical name
- `test_onboarding_blocks_on_a_matching_registration_number` — Onboarding blocks on a matching registration number
- `test_the_two_signals_are_reported_separately` — The two signals are reported separately
- `test_an_override_with_a_reason_is_allowed_and_recorded` — An override with a reason is allowed and recorded
- `test_the_override_is_audited` — The override is audited
- `test_an_unrelated_name_onboards_cleanly` — An unrelated name onboards cleanly
- `test_a_party_in_another_tenant_is_not_a_duplicate` — A party in another tenant is not a duplicate
- `test_a_party_without_a_name_is_refused` — A party without a name is refused
- `test_an_unknown_entity_type_is_refused` — An unknown entity type is refused
- `test_linking_a_contract_keeps_the_free_text_field_in_step` — Linking a contract keeps the free text field in step
- `test_addenda_are_numbered_sequentially_per_parent` — Addenda are numbered sequentially per parent
- `test_a_second_parent_starts_its_own_addendum_numbering` — A second parent starts its own addendum numbering
- `test_only_addenda_are_numbered` — Only addenda are numbered
- `test_an_agreement_cannot_be_related_to_itself` — An agreement cannot be related to itself
- `test_an_unknown_relationship_kind_is_refused` — An unknown relationship kind is refused
- `test_relating_twice_is_idempotent` — Relating twice is idempotent
- `test_an_addendum_inherits_its_parents_context` — An addendum inherits its parents context
- `test_inheriting_does_not_overwrite_what_is_already_set` — Inheriting does not overwrite what is already set
- `test_the_history_tree_shows_both_directions` — The history tree shows both directions
- `test_folder_paths_are_materialised` — Folder paths are materialised
- `test_a_duplicate_path_is_refused` — A duplicate path is refused
- `test_moving_a_folder_rewrites_the_whole_subtree` — Moving a folder rewrites the whole subtree
- `test_a_folder_cannot_be_moved_inside_itself` — A folder cannot be moved inside itself
- `test_a_folder_cannot_contain_itself` — A folder cannot contain itself
- `test_a_slash_in_a_folder_name_cannot_forge_a_path` — A slash in a folder name cannot forge a path
- `test_role_visibility_filters_the_tree` — Role visibility filters the tree
- `test_house_wide_and_type_specific_fields_both_apply` — House wide and type specific fields both apply
- `test_custom_values_are_validated_against_their_type` — Custom values are validated against their type
- `test_custom_values_are_stored_json_safe` — Custom values are stored json safe
- `test_a_required_custom_field_is_enforced` — A required custom field is enforced
- `test_describing_fields_carries_the_current_values` — Describing fields carries the current values
- `test_free_text_matches_the_body` — Free text matches the body
- `test_a_reference_number_is_searchable` — A reference number is searchable
- `test_filters_narrow_the_result` — Filters narrow the result
- `test_a_value_band_filters` — A value band filters
- `test_a_date_range_filters` — A date range filters
- `test_a_folder_filter_includes_everything_beneath_it` — A folder filter includes everything beneath it
- `test_archived_agreements_are_excluded_by_default` — Archived agreements are excluded by default
- `test_a_clause_filter_finds_agreements_composing_it` — A clause filter finds agreements composing it
- `test_another_tenants_agreements_never_appear` — Another tenants agreements never appear
- `test_facets_count_the_whole_result_not_the_page` — Facets count the whole result not the page
- `test_paging_walks_the_whole_set` — Paging walks the whole set
- `test_a_snippet_highlights_the_query_terms` — A snippet highlights the query terms
- `test_a_snippet_is_trimmed_around_the_hit` — A snippet is trimmed around the hit
- `test_a_snippet_falls_back_to_the_opening_when_nothing_matches` — A snippet falls back to the opening when nothing matches
- `test_an_empty_body_produces_no_snippet` — An empty body produces no snippet

</details>

**UAT-SOW-24-02** · Run the tagging suite

*Why it matters:* Smart signature tagging — find the signature blocks instead of dragging boxes.

*Automated by:* `test_tagging.py` — 15 tests

<details><summary>Tests in this script</summary>

- `test_finds_signature_anchors_in_a_real_pdf` — Finds signature anchors in a real PDF
- `test_coordinates_are_normalised_with_y_from_the_top` — Coordinates are normalised with y from the top
- `test_left_and_right_columns_are_distinguished` — Left and right columns are distinguished
- `test_supporting_fields_are_classified` — Supporting fields are classified
- `test_no_anchors_in_ordinary_prose` — No anchors in ordinary prose
- `test_template_anchor_is_honoured` — Template anchor is honoured
- `test_unreadable_input_returns_empty_not_an_exception` — Unreadable input returns empty not an exception
- `test_tabs_are_distributed_across_signers` — Tabs are distributed across signers
- `test_supporting_fields_follow_their_nearest_signature` — Supporting fields follow their nearest signature
- `test_tabs_stay_on_the_page` — Tabs stay on the page
- `test_signature_tabs_are_required` — Signature tabs are required
- `test_no_signers_is_explained_not_silently_empty` — No signers is explained not silently empty
- `test_undetectable_document_explains_itself` — Undetectable document explains itself
- `test_confidence_prefers_explicit_phrases` — Confidence prefers explicit phrases
- `test_runs_on_one_line_collapse_to_a_single_tab` — Runs on one line collapse to a single tab

</details>


#### SOW-25

**UAT-SOW-25-01** · Run the archive retention suite

*Why it matters:* Archive and purge — the 10-year retention tier with a 1-year hot search window.

*Automated by:* `test_archive_retention.py` — 12 tests

<details><summary>Tests in this script</summary>

- `test_archives_contract_past_the_hot_window` — Archives contract past the hot window
- `test_leaves_contracts_inside_the_hot_window_alone` — Leaves contracts inside the hot window alone
- `test_legal_hold_blocks_archival` — Legal hold blocks archival
- `test_drafts_are_never_archived` — Drafts are never archived
- `test_archive_is_idempotent` — Archive is idempotent
- `test_archive_writes_an_audit_entry` — Archive writes an audit entry
- `test_archived_files_move_to_the_cold_prefix` — Archived files move to the cold prefix
- `test_purges_contract_past_retention` — Purges contract past retention
- `test_does_not_purge_inside_retention` — Does not purge inside retention
- `test_legal_hold_blocks_purge` — Legal hold blocks purge
- `test_purge_removes_children_and_records_evidence` — Purge removes children and records evidence
- `test_eligibility_gate_is_shared_by_both_sweeps` — Eligibility gate is shared by both sweeps

</details>


#### SOW-26

**UAT-SOW-26-01** · Run the renewals and webhooks suite

*Why it matters:* The renewal sweep and webhook dispatch (Phase 10 — coverage on two beat-driven services).

*Automated by:* `test_renewals_and_webhooks.py` — 34 tests

<details><summary>Tests in this script</summary>

- `test_a_contract_inside_the_window_is_flagged_expiring` — A contract inside the window is flagged expiring
- `test_a_contract_beyond_the_window_is_left_alone` — A contract beyond the window is left alone
- `test_a_contract_past_its_end_date_expires` — A contract past its end date expires
- `test_a_contract_already_expiring_still_expires` — A contract already expiring still expires
- `test_a_contract_with_no_end_date_is_untouched` — A contract with no end date is untouched
- `test_a_draft_is_not_swept` — A draft is not swept
- `test_the_expired_notice_fires_once_not_on_every_beat` — The expired notice fires once not on every beat
- `test_the_follow_up_reminders_fire_at_their_thresholds` — The follow up reminders fire at their thresholds
- `test_the_same_threshold_does_not_re_fire` — The same threshold does not re fire
- `test_a_reminder_is_skipped_when_there_is_nobody_to_tell` — A reminder is skipped when there is nobody to tell
- `test_a_pending_obligation_past_its_date_becomes_overdue` — A pending obligation past its date becomes overdue
- `test_a_completed_obligation_is_not_reopened` — A completed obligation is not reopened
- `test_renewing_creates_a_draft_successor_and_closes_the_original` — Renewing creates a draft successor and closes the original
- `test_the_successor_starts_the_day_after_the_original_ends` — The successor starts the day after the original ends
- `test_the_successor_inherits_the_original_term_length` — The successor inherits the original term length
- `test_a_contract_with_no_dates_renews_for_twelve_months` — A contract with no dates renews for twelve months
- `test_explicit_dates_win_over_the_defaults` — Explicit dates win over the defaults
- `test_a_draft_cannot_be_renewed` — A draft cannot be renewed
- `test_the_successor_gets_its_own_reference_and_first_version` — The successor gets its own reference and first version
- `test_the_chain_links_both_ways` — The chain links both ways
- `test_a_leap_day_renewal_lands_on_a_real_date` — A leap day renewal lands on a real date
- `test_the_signature_binds_the_timestamp_to_the_body` — The signature binds the timestamp to the body
- `test_a_different_secret_produces_a_different_signature` — A different secret produces a different signature
- `test_the_signature_is_verifiable_by_a_receiver` — The signature is verifiable by a receiver
- `test_a_new_secret_is_long_enough_to_be_a_secret` — A new secret is long enough to be a secret
- `test_subscription_matching` — Subscription matching
- `test_a_successful_delivery_is_recorded` — A successful delivery is recorded
- `test_a_non_2xx_response_is_a_failure` — A non 2xx response is a failure
- `test_an_unreachable_endpoint_does_not_take_down_the_caller` — An unreachable endpoint does not take down the caller
- `test_an_inactive_endpoint_receives_nothing` — An inactive endpoint receives nothing
- `test_an_endpoint_that_did_not_subscribe_receives_nothing` — An endpoint that did not subscribe receives nothing
- `test_another_tenants_endpoint_is_never_called` — Another tenants endpoint is never called
- `test_the_delivery_carries_the_signature_and_event_headers` — The delivery carries the signature and event headers
- `test_dispatch_with_no_endpoints_is_a_cheap_no_op` — Dispatch with no endpoints is a cheap no op

</details>


#### SOW-27

**UAT-SOW-27-01** · Run the renewals and webhooks suite

*Why it matters:* The renewal sweep and webhook dispatch (Phase 10 — coverage on two beat-driven services).

*Automated by:* `test_renewals_and_webhooks.py` — 34 tests

<details><summary>Tests in this script</summary>

- `test_a_contract_inside_the_window_is_flagged_expiring` — A contract inside the window is flagged expiring
- `test_a_contract_beyond_the_window_is_left_alone` — A contract beyond the window is left alone
- `test_a_contract_past_its_end_date_expires` — A contract past its end date expires
- `test_a_contract_already_expiring_still_expires` — A contract already expiring still expires
- `test_a_contract_with_no_end_date_is_untouched` — A contract with no end date is untouched
- `test_a_draft_is_not_swept` — A draft is not swept
- `test_the_expired_notice_fires_once_not_on_every_beat` — The expired notice fires once not on every beat
- `test_the_follow_up_reminders_fire_at_their_thresholds` — The follow up reminders fire at their thresholds
- `test_the_same_threshold_does_not_re_fire` — The same threshold does not re fire
- `test_a_reminder_is_skipped_when_there_is_nobody_to_tell` — A reminder is skipped when there is nobody to tell
- `test_a_pending_obligation_past_its_date_becomes_overdue` — A pending obligation past its date becomes overdue
- `test_a_completed_obligation_is_not_reopened` — A completed obligation is not reopened
- `test_renewing_creates_a_draft_successor_and_closes_the_original` — Renewing creates a draft successor and closes the original
- `test_the_successor_starts_the_day_after_the_original_ends` — The successor starts the day after the original ends
- `test_the_successor_inherits_the_original_term_length` — The successor inherits the original term length
- `test_a_contract_with_no_dates_renews_for_twelve_months` — A contract with no dates renews for twelve months
- `test_explicit_dates_win_over_the_defaults` — Explicit dates win over the defaults
- `test_a_draft_cannot_be_renewed` — A draft cannot be renewed
- `test_the_successor_gets_its_own_reference_and_first_version` — The successor gets its own reference and first version
- `test_the_chain_links_both_ways` — The chain links both ways
- `test_a_leap_day_renewal_lands_on_a_real_date` — A leap day renewal lands on a real date
- `test_the_signature_binds_the_timestamp_to_the_body` — The signature binds the timestamp to the body
- `test_a_different_secret_produces_a_different_signature` — A different secret produces a different signature
- `test_the_signature_is_verifiable_by_a_receiver` — The signature is verifiable by a receiver
- `test_a_new_secret_is_long_enough_to_be_a_secret` — A new secret is long enough to be a secret
- `test_subscription_matching` — Subscription matching
- `test_a_successful_delivery_is_recorded` — A successful delivery is recorded
- `test_a_non_2xx_response_is_a_failure` — A non 2xx response is a failure
- `test_an_unreachable_endpoint_does_not_take_down_the_caller` — An unreachable endpoint does not take down the caller
- `test_an_inactive_endpoint_receives_nothing` — An inactive endpoint receives nothing
- `test_an_endpoint_that_did_not_subscribe_receives_nothing` — An endpoint that did not subscribe receives nothing
- `test_another_tenants_endpoint_is_never_called` — Another tenants endpoint is never called
- `test_the_delivery_carries_the_signature_and_event_headers` — The delivery carries the signature and event headers
- `test_dispatch_with_no_endpoints_is_a_cheap_no_op` — Dispatch with no endpoints is a cheap no op

</details>


#### SOW-28

**UAT-SOW-28-01** · Run the change flows suite

*Why it matters:* Post-execution changes: amendments, terminations, renewal notices, obligation sweeps.

*Automated by:* `test_change_flows.py` — 39 tests

<details><summary>Tests in this script</summary>

- `test_a_draft_cannot_be_amended` — A draft cannot be amended
- `test_an_agreement_under_legal_hold_cannot_be_amended` — An agreement under legal hold cannot be amended
- `test_an_amendment_is_a_separate_draft_leaving_the_parent_in_force` — An amendment is a separate draft leaving the parent in force
- `test_the_amendment_inherits_the_parents_commercial_context` — The amendment inherits the parents commercial context
- `test_the_amendment_is_linked_to_what_it_amends` — The amendment is linked to what it amends
- `test_the_impact_reports_what_actually_moved` — The impact reports what actually moved
- `test_the_impact_reports_clauses_added_and_removed` — The impact reports clauses added and removed
- `test_an_unsigned_amendment_cannot_take_effect` — An unsigned amendment cannot take effect
- `test_executing_an_amendment_records_the_impact_and_supersedes_the_parent` — Executing an amendment records the impact and supersedes the parent
- `test_executing_something_that_is_not_an_amendment_is_refused` — Executing something that is not an amendment is refused
- `test_a_termination_needs_a_reason` — A termination needs a reason
- `test_an_unknown_reason_code_is_refused` — An unknown reason code is refused
- `test_a_draft_cannot_be_terminated` — A draft cannot be terminated
- `test_legal_hold_blocks_termination` — Legal hold blocks termination
- `test_only_one_termination_request_can_be_open` — Only one termination request can be open
- `test_the_effective_date_defaults_to_the_notice_period` — The effective date defaults to the notice period
- `test_a_request_does_not_terminate_anything_by_itself` — A request does not terminate anything by itself
- `test_a_role_that_is_not_required_cannot_decide` — A role that is not required cannot decide
- `test_nobody_decides_twice` — Nobody decides twice
- `test_it_stays_pending_until_every_required_role_has_approved` — It stays pending until every required role has approved
- `test_one_rejection_ends_the_request` — One rejection ends the request
- `test_an_unapproved_termination_cannot_be_executed` — An unapproved termination cannot be executed
- `test_executing_terminates_and_closes_open_obligations` — Executing terminates and closes open obligations
- `test_the_notice_is_generated_from_the_recorded_request` — The notice is generated from the recorded request
- `test_the_default_schedule_is_ninety_sixty_thirty` — The default schedule is ninety sixty thirty
- `test_a_per_agreement_schedule_overrides_the_default` — A per agreement schedule overrides the default
- `test_a_schedule_is_deduplicated_and_ordered` — A schedule is deduplicated and ordered
- `test_an_empty_schedule_is_refused` — An empty schedule is refused
- `test_an_absurd_notice_period_is_refused` — An absurd notice period is refused
- `test_due_notices_reflect_how_close_expiry_is` — Due notices reflect how close expiry is
- `test_an_agreement_with_no_end_date_raises_no_notices` — An agreement with no end date raises no notices
- `test_the_rollup_spans_every_agreement` — The rollup spans every agreement
- `test_the_rollup_counts_what_an_operations_view_needs` — The rollup counts what an operations view needs
- `test_the_rollup_can_be_filtered_to_one_owner` — The rollup can be filtered to one owner
- `test_another_tenants_obligations_never_appear` — Another tenants obligations never appear
- `test_the_sweep_marks_overdue_and_reminds` — The sweep marks overdue and reminds
- `test_the_sweep_does_not_repeat_a_reminder` — The sweep does not repeat a reminder
- `test_the_sweep_escalates_to_the_contract_owner_once` — The sweep escalates to the contract owner once
- `test_the_sweep_ignores_obligations_on_a_terminated_agreement` — The sweep ignores obligations on a terminated agreement

</details>


#### SOW-29

**UAT-SOW-29-01** · Run the access control suite

*Why it matters:* Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

*Automated by:* `test_access_control.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_builtin_roles_carry_what_they_should` — The builtin roles carry what they should
- `test_an_unknown_role_degrades_to_viewer_not_to_nothing` — An unknown role degrades to viewer not to nothing
- `test_a_custom_role_extends_its_base` — A custom role extends its base
- `test_a_revoke_always_wins` — A revoke always wins
- `test_an_inactive_custom_role_falls_back` — An inactive custom role falls back
- `test_require_raises_rather_than_returning_false` — Require raises rather than returning false
- `test_the_author_of_an_agreement_cannot_approve_it` — The author of an agreement cannot approve it
- `test_somebody_else_can_approve_it` — Somebody else can approve it
- `test_the_rule_is_per_object_not_global` — The rule is per object not global
- `test_a_block_is_recorded` — A block is recorded
- `test_an_override_needs_a_reason_and_is_audited_loudly` — An override needs a reason and is audited loudly
- `test_a_webhook_creator_cannot_reveal_its_own_secret` — A webhook creator cannot reveal its own secret
- `test_an_unrelated_action_is_not_segregated` — An unrelated action is not segregated
- `test_only_sensitive_actions_need_step_up` — Only sensitive actions need step up
- `test_a_sensitive_action_without_a_challenge_demands_one` — A sensitive action without a challenge demands one
- `test_a_satisfied_challenge_lets_the_action_through` — A satisfied challenge lets the action through
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_a_challenge_cannot_be_replayed_against_another_object` — A challenge cannot be replayed against another object
- `test_a_challenge_cannot_be_reused_for_a_different_action` — A challenge cannot be reused for a different action
- `test_a_wrong_password_does_not_satisfy_a_challenge` — A wrong password does not satisfy a challenge
- `test_repeated_wrong_answers_burn_the_challenge` — Repeated wrong answers burn the challenge
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_somebody_elses_challenge_cannot_be_answered` — Somebody elses challenge cannot be answered
- `test_an_ordinary_agreement_is_visible_to_everyone` — An ordinary agreement is visible to everyone
- `test_a_confidential_agreement_is_not` — A confidential agreement is not
- `test_the_owner_can_always_see_their_own` — The owner can always see their own
- `test_an_explicit_grant_opens_it` — An explicit grant opens it
- `test_a_role_grant_opens_it_for_that_role` — A role grant opens it for that role
- `test_an_expired_grant_closes_again` — An expired grant closes again
- `test_a_refused_read_is_logged` — A refused read is logged
- `test_break_glass_needs_a_reason` — Break glass needs a reason
- `test_break_glass_grants_access_and_shouts_about_it` — Break glass grants access and shouts about it
- `test_a_link_resolves_to_its_record` — A link resolves to its record
- `test_only_the_hash_is_stored` — Only the hash is stored
- `test_a_revoked_link_stops_resolving` — A revoked link stops resolving
- `test_an_expired_link_stops_resolving` — An expired link stops resolving
- `test_a_wrong_token_resolves_to_nothing` — A wrong token resolves to nothing
- `test_an_absurd_duration_is_refused` — An absurd duration is refused
- `test_the_expiry_sweep_is_idempotent` — The expiry sweep is idempotent
- `test_placing_a_hold_sets_the_flag_every_retention_path_reads` — Placing a hold sets the flag every retention path reads
- `test_a_hold_needs_a_matter_and_something_to_hold` — A hold needs a matter and something to hold
- `test_a_hold_over_a_missing_agreement_is_refused` — A hold over a missing agreement is refused
- `test_releasing_needs_a_reason` — Releasing needs a reason
- `test_releasing_the_only_hold_clears_the_flag` — Releasing the only hold clears the flag
- `test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers` — Releasing one matter does not expose an agreement another still covers
- `test_a_released_hold_cannot_be_released_twice` — A released hold cannot be released twice
- `test_extending_a_hold_covers_the_new_agreements` — Extending a hold covers the new agreements
- `test_the_export_set_carries_audit_chain_positions` — The export set carries audit chain positions
- `test_reconcile_repairs_a_drifted_flag` — Reconcile repairs a drifted flag

</details>


#### SOW-30

**UAT-SOW-30-01** · Run the analytics suite

*Why it matters:* Analytics: KPIs, bottlenecks, workload, compliance posture and MIS trends.

*Automated by:* `test_analytics.py` — 25 tests

<details><summary>Tests in this script</summary>

- `test_cycle_time_is_measured_from_the_audit_log` — Cycle time is measured from the audit log
- `test_an_unfinished_agreement_is_excluded_not_counted_as_zero` — An unfinished agreement is excluded not counted as zero
- `test_cycle_times_are_broken_out_by_agreement_type` — Cycle times are broken out by agreement type
- `test_the_median_survives_one_pathological_agreement` — The median survives one pathological agreement
- `test_an_empty_repository_reports_none_rather_than_zero` — An empty repository reports none rather than zero
- `test_the_bottleneck_is_the_slowest_stage` — The bottleneck is the slowest stage
- `test_sla_adherence_is_reported_with_its_sample` — SLA adherence is reported with its sample
- `test_a_stage_with_no_sla_reports_none_not_a_hundred_percent` — A stage with no SLA reports none not a hundred percent
- `test_workload_is_ordered_by_what_is_still_open` — Workload is ordered by what is still open
- `test_overdue_reviews_are_counted_against_the_reviewer` — Overdue reviews are counted against the reviewer
- `test_escalations_are_trended_and_timed` — Escalations are trended and timed
- `test_the_renewal_pipeline_buckets_by_urgency` — The renewal pipeline buckets by urgency
- `test_a_draft_is_not_in_the_renewal_pipeline` — A draft is not in the renewal pipeline
- `test_negotiation_effort_counts_redline_rounds` — Negotiation effort counts redline rounds
- `test_clause_pressure_ranks_what_counterparties_push_back_on` — Clause pressure ranks what counterparties push back on
- `test_compliance_posture_is_computed_live` — Compliance posture is computed live
- `test_the_volume_trend_aligns_year_on_year_by_period` — The volume trend aligns year on year by period
- `test_the_trend_can_be_bucketed_by_week` — The trend can be bucketed by week
- `test_an_unknown_granularity_is_refused` — An unknown granularity is refused
- `test_segmentation_uses_the_party_record_for_region` — Segmentation uses the party record for region
- `test_unsegmented_rows_are_labelled_rather_than_dropped` — Unsegmented rows are labelled rather than dropped
- `test_my_dashboard_shows_only_my_work` — My dashboard shows only my work
- `test_a_role_assigned_step_reaches_everyone_in_that_role` — A role assigned step reaches everyone in that role
- `test_my_dashboard_lists_my_overdue_obligations` — My dashboard lists my overdue obligations
- `test_my_dashboard_lists_renewals_i_own` — My dashboard lists renewals i own

</details>


#### SOW-31

**UAT-SOW-31-01** · Run the exports suite

*Why it matters:* Repository and report exports.

*Automated by:* `test_exports.py` — 16 tests

<details><summary>Tests in this script</summary>

- `test_the_workbook_is_a_real_spreadsheet` — The workbook is a real spreadsheet
- `test_the_first_sheet_records_what_the_export_actually_is` — The first sheet records what the export actually is
- `test_an_unfiltered_export_says_so_rather_than_leaving_the_sheet_blank` — An unfiltered export says so rather than leaving the sheet blank
- `test_dates_stay_dates_and_numbers_stay_numbers` — Dates stay dates and numbers stay numbers
- `test_a_reference_number_survives_as_text` — A reference number survives as text
- `test_filters_narrow_the_export` — Filters narrow the export
- `test_obligations_can_be_exported` — Obligations can be exported
- `test_parties_export_counts_their_agreements` — Parties export counts their agreements
- `test_the_audit_log_can_be_exported_in_chain_order` — The audit log can be exported in chain order
- `test_another_tenants_rows_are_never_exported` — Another tenants rows are never exported
- `test_an_unknown_export_kind_is_refused` — An unknown export kind is refused
- `test_an_empty_repository_still_produces_a_usable_workbook` — An empty repository still produces a usable workbook
- `test_running_an_export_records_a_downloadable_job` — Running an export records a downloadable job
- `test_the_generated_file_is_actually_in_storage` — The generated file is actually in storage
- `test_a_failed_export_leaves_a_visible_failed_job` — A failed export leaves a visible failed job
- `test_the_filename_names_the_export_and_the_day` — The filename names the export and the day

</details>


#### SOW-32

**UAT-SOW-32-01** · Run the adoption suite

*Why it matters:* Contextual help, knowledge base, training and guided actions (Phase 9, items 1-4).

*Automated by:* `test_adoption.py` — 47 tests

<details><summary>Tests in this script</summary>

- `test_seeding_is_idempotent` — Seeding is idempotent
- `test_a_deploy_does_not_revert_an_edit` — A deploy does not revert an edit
- `test_an_edit_can_be_undone` — An edit can be undone
- `test_editing_help_is_audited` — Editing help is audited
- `test_a_missing_translation_falls_back_per_topic` — A missing translation falls back per topic
- `test_an_unknown_locale_falls_back_rather_than_failing` — An unknown locale falls back rather than failing
- `test_help_can_be_filtered_to_one_screen` — Help can be filtered to one screen
- `test_an_article_round_trips` — An article round trips
- `test_two_articles_cannot_share_an_address` — Two articles cannot share an address
- `test_an_article_with_no_audience_is_for_everyone` — An article with no audience is for everyone
- `test_unpublished_articles_are_not_listed` — Unpublished articles are not listed
- `test_search_looks_in_the_body` — Search looks in the body
- `test_every_category_is_listed_even_when_empty` — Every category is listed even when empty
- `test_the_answer_key_never_leaves_the_server` — The answer key never leaves the server
- `test_passing_issues_a_certificate_that_expires` — Passing issues a certificate that expires
- `test_a_lapsed_certificate_reports_as_expired` — A lapsed certificate reports as expired
- `test_failing_reports_only_the_questions_that_were_wrong` — Failing reports only the questions that were wrong
- `test_a_failed_retake_does_not_revoke_a_certificate` — A failed retake does not revoke a certificate
- `test_a_repeat_pass_keeps_the_same_certificate_number` — A repeat pass keeps the same certificate number
- `test_a_wrong_number_of_answers_is_refused` — A wrong number of answers is refused
- `test_a_trivial_quiz_is_refused` — A trivial quiz is refused
- `test_a_question_pointing_nowhere_is_refused` — A question pointing nowhere is refused
- `test_module_progress_accumulates` — Module progress accumulates
- `test_a_module_outside_the_course_is_refused` — A module outside the course is refused
- `test_my_training_reports_what_is_outstanding` — My training reports what is outstanding
- `test_the_report_counts_people_not_enrolments` — The report counts people not enrolments
- `test_an_expired_certificate_is_not_counted_as_trained` — An expired certificate is not counted as trained
- `test_registering_twice_does_not_take_two_places` — Registering twice does not take two places
- `test_a_full_session_is_refused` — A full session is refused
- `test_a_past_session_cannot_be_joined` — A past session cannot be joined
- `test_attendance_is_separate_from_registration` — Attendance is separate from registration
- `test_attendance_for_somebody_outside_the_workspace_is_refused` — Attendance for somebody outside the workspace is refused
- `test_certificate_validity_clamps_the_day` — Certificate validity clamps the day
- `test_a_closed_agreement_gets_no_suggestions` — A closed agreement gets no suggestions
- `test_missing_dates_are_raised_before_they_bite` — Missing dates are raised before they bite
- `test_auto_renew_without_an_expiry_is_critical` — Auto renew without an expiry is critical
- `test_an_expiring_agreement_says_how_long_is_left` — An expiring agreement says how long is left
- `test_a_running_workflow_redirects_rather_than_offering_a_status_change` — A running workflow redirects rather than offering a status change
- `test_the_stage_tracker_marks_where_it_is` — The stage tracker marks where it is
- `test_prefill_says_nothing_when_there_is_nothing_to_say` — Prefill says nothing when there is nothing to say
- `test_prefill_comes_from_what_this_user_did_last` — Prefill comes from what this user did last
- `test_renewal_type_is_not_carried_across_agreement_types` — Renewal type is not carried across agreement types
- `test_workspace_actions_surface_stalled_drafts` — Workspace actions surface stalled drafts
- `test_overdue_obligations_are_read_from_the_date_not_the_status` — Overdue obligations are read from the date not the status
- `test_a_new_workspace_starts_with_real_content` — A new workspace starts with real content
- `test_seeded_courses_carry_a_markable_quiz` — Seeded courses carry a markable quiz
- `test_a_seeded_course_can_actually_be_passed` — A seeded course can actually be passed

</details>


#### SOW-33

**UAT-SOW-33-01** · Run the adoption suite

*Why it matters:* Contextual help, knowledge base, training and guided actions (Phase 9, items 1-4).

*Automated by:* `test_adoption.py` — 47 tests

<details><summary>Tests in this script</summary>

- `test_seeding_is_idempotent` — Seeding is idempotent
- `test_a_deploy_does_not_revert_an_edit` — A deploy does not revert an edit
- `test_an_edit_can_be_undone` — An edit can be undone
- `test_editing_help_is_audited` — Editing help is audited
- `test_a_missing_translation_falls_back_per_topic` — A missing translation falls back per topic
- `test_an_unknown_locale_falls_back_rather_than_failing` — An unknown locale falls back rather than failing
- `test_help_can_be_filtered_to_one_screen` — Help can be filtered to one screen
- `test_an_article_round_trips` — An article round trips
- `test_two_articles_cannot_share_an_address` — Two articles cannot share an address
- `test_an_article_with_no_audience_is_for_everyone` — An article with no audience is for everyone
- `test_unpublished_articles_are_not_listed` — Unpublished articles are not listed
- `test_search_looks_in_the_body` — Search looks in the body
- `test_every_category_is_listed_even_when_empty` — Every category is listed even when empty
- `test_the_answer_key_never_leaves_the_server` — The answer key never leaves the server
- `test_passing_issues_a_certificate_that_expires` — Passing issues a certificate that expires
- `test_a_lapsed_certificate_reports_as_expired` — A lapsed certificate reports as expired
- `test_failing_reports_only_the_questions_that_were_wrong` — Failing reports only the questions that were wrong
- `test_a_failed_retake_does_not_revoke_a_certificate` — A failed retake does not revoke a certificate
- `test_a_repeat_pass_keeps_the_same_certificate_number` — A repeat pass keeps the same certificate number
- `test_a_wrong_number_of_answers_is_refused` — A wrong number of answers is refused
- `test_a_trivial_quiz_is_refused` — A trivial quiz is refused
- `test_a_question_pointing_nowhere_is_refused` — A question pointing nowhere is refused
- `test_module_progress_accumulates` — Module progress accumulates
- `test_a_module_outside_the_course_is_refused` — A module outside the course is refused
- `test_my_training_reports_what_is_outstanding` — My training reports what is outstanding
- `test_the_report_counts_people_not_enrolments` — The report counts people not enrolments
- `test_an_expired_certificate_is_not_counted_as_trained` — An expired certificate is not counted as trained
- `test_registering_twice_does_not_take_two_places` — Registering twice does not take two places
- `test_a_full_session_is_refused` — A full session is refused
- `test_a_past_session_cannot_be_joined` — A past session cannot be joined
- `test_attendance_is_separate_from_registration` — Attendance is separate from registration
- `test_attendance_for_somebody_outside_the_workspace_is_refused` — Attendance for somebody outside the workspace is refused
- `test_certificate_validity_clamps_the_day` — Certificate validity clamps the day
- `test_a_closed_agreement_gets_no_suggestions` — A closed agreement gets no suggestions
- `test_missing_dates_are_raised_before_they_bite` — Missing dates are raised before they bite
- `test_auto_renew_without_an_expiry_is_critical` — Auto renew without an expiry is critical
- `test_an_expiring_agreement_says_how_long_is_left` — An expiring agreement says how long is left
- `test_a_running_workflow_redirects_rather_than_offering_a_status_change` — A running workflow redirects rather than offering a status change
- `test_the_stage_tracker_marks_where_it_is` — The stage tracker marks where it is
- `test_prefill_says_nothing_when_there_is_nothing_to_say` — Prefill says nothing when there is nothing to say
- `test_prefill_comes_from_what_this_user_did_last` — Prefill comes from what this user did last
- `test_renewal_type_is_not_carried_across_agreement_types` — Renewal type is not carried across agreement types
- `test_workspace_actions_surface_stalled_drafts` — Workspace actions surface stalled drafts
- `test_overdue_obligations_are_read_from_the_date_not_the_status` — Overdue obligations are read from the date not the status
- `test_a_new_workspace_starts_with_real_content` — A new workspace starts with real content
- `test_seeded_courses_carry_a_markable_quiz` — Seeded courses carry a markable quiz
- `test_a_seeded_course_can_actually_be_passed` — A seeded course can actually be passed

</details>



### Branchless Banking Operations — RFP §4a(ii)

#### BB-01

**UAT-BB-01-01** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)

**UAT-BB-01-02** · A signing link is useless once the envelope is voided

*Why it matters:* BB-01. A voided envelope whose link still works is voided in name only.

*Automated by:* `test_journeys_e2e.py::test_a_signing_link_is_useless_once_the_envelope_is_voided` (line 428)

**UAT-BB-01-03** · Run the journeys e2e suite

*Why it matters:* End-to-end journey tests (Phase 10).

*Automated by:* `test_journeys_e2e.py` — 1 tests

<details><summary>Tests in this script</summary>

- `test_one_workspace_cannot_read_anothers_agreements` — One workspace cannot read anothers agreements

</details>

**UAT-BB-01-04** · Run the signing token security suite

*Why it matters:* Signing-portal access-token security — verifies that: - the raw URL token is never stored in the DB (only the SHA-256 hash and Fernet ciphertext) - lookups by hashed token work - expired tokens look like 'not found' (don't leak existence) - decrypt round-trips for reminders - void wipes hash + ciphertext + expiry

*Automated by:* `test_signing_token_security.py` — 6 tests

<details><summary>Tests in this script</summary>

- `test_raw_token_is_not_persisted` — Raw token is not persisted
- `test_lookup_by_hash_finds_recipient` — Lookup by hash finds recipient
- `test_wrong_token_returns_none` — Wrong token returns none
- `test_expired_token_returns_none` — Expired token returns none
- `test_decrypt_for_reminder_round_trips` — Decrypt for reminder round trips
- `test_clear_token_wipes_all_three_columns` — Clear token wipes all three columns

</details>


#### BB-02

**UAT-BB-02-01** · Journey 1 bbcorp intake to execution

*Why it matters:* The whole spine in one pass: an approved template, a structured intake, a generated draft, a routed approval, an envelope, and a counterparty signature from an unauthenticated link.

*Automated by:* `test_journeys_e2e.py::test_journey_1_bbcorp_intake_to_execution` (line 145)

**UAT-BB-02-02** · Run the signing engine suite

*Why it matters:* The e-signature engine (Phase 10 — coverage on `signing_service`).

*Automated by:* `test_signing_engine.py` — 44 tests

<details><summary>Tests in this script</summary>

- `test_an_envelope_needs_a_signer` — An envelope needs a signer
- `test_recipients_keep_the_order_they_were_given` — Recipients keep the order they were given
- `test_an_internal_signer_is_bound_to_their_workspace_identity` — An internal signer is bound to their workspace identity
- `test_a_user_in_another_tenant_is_not_matched` — A user in another tenant is not matched
- `test_an_unsent_envelope_has_no_tokens` — An unsent envelope has no tokens
- `test_sending_snapshots_what_is_being_signed` — Sending snapshots what is being signed
- `test_sending_twice_is_refused` — Sending twice is refused
- `test_sequential_sending_invites_only_the_first_signer` — Sequential sending invites only the first signer
- `test_parallel_sending_invites_everybody_at_once` — Parallel sending invites everybody at once
- `test_cc_recipients_are_notified_immediately_in_either_order` — CC recipients are notified immediately in either order
- `test_a_cc_is_never_anybodys_turn` — A CC is never anybodys turn
- `test_in_parallel_mode_it_is_always_everybodys_turn` — In parallel mode it is always everybodys turn
- `test_signing_out_of_turn_is_refused` — Signing out of turn is refused
- `test_a_sequential_signature_invites_the_next_person` — A sequential signature invites the next person
- `test_the_last_signature_completes_the_envelope` — The last signature completes the envelope
- `test_signing_twice_is_refused` — Signing twice is refused
- `test_a_cc_cannot_sign` — A CC cannot sign
- `test_a_completed_envelope_cannot_be_signed_again` — A completed envelope cannot be signed again
- `test_a_stale_envelope_read_cannot_overwrite_a_fresh_signature` — A stale envelope read cannot overwrite a fresh signature
- `test_the_lock_version_advances_on_every_claim` — The lock version advances on every claim
- `test_a_real_png_is_accepted` — A real png is accepted
- `test_a_bad_signature_image_is_rejected` — A bad signature image is rejected
- `test_an_oversized_image_is_rejected` — An oversized image is rejected
- `test_a_drawn_signature_without_an_image_is_refused` — A drawn signature without an image is refused
- `test_a_drawn_signature_is_stored` — A drawn signature is stored
- `test_an_unknown_signature_kind_falls_back_to_typed` — An unknown signature kind falls back to typed
- `test_signature_initials_and_date_tabs_fill_themselves` — Signature initials and date tabs fill themselves
- `test_a_required_text_tab_blocks_signing_until_filled` — A required text tab blocks signing until filled
- `test_a_filled_required_tab_lets_signing_through` — A filled required tab lets signing through
- `test_a_checkbox_tab_reads_the_usual_truthy_spellings` — A checkbox tab reads the usual truthy spellings
- `test_a_recipient_with_no_tabs_is_not_blocked` — A recipient with no tabs is not blocked
- `test_initials_of_a_single_word_name` — Initials of a single word name
- `test_declining_ends_the_envelope_for_everyone` — Declining ends the envelope for everyone
- `test_declining_twice_is_refused` — Declining twice is refused
- `test_somebody_who_signed_cannot_then_decline` — Somebody who signed cannot then decline
- `test_voiding_kills_every_link` — Voiding kills every link
- `test_a_completed_envelope_cannot_be_voided` — A completed envelope cannot be voided
- `test_reminding_somebody_who_has_signed_is_refused` — Reminding somebody who has signed is refused
- `test_a_reminder_is_recorded` — A reminder is recorded
- `test_opening_the_link_is_recorded_once` — Opening the link is recorded once
- `test_the_current_envelope_is_the_newest_one` — The current envelope is the newest one
- `test_the_current_envelope_is_stable_when_timestamps_tie` — The current envelope is stable when timestamps tie
- `test_the_active_envelope_ignores_terminal_ones` — The active envelope ignores terminal ones
- `test_deleting_a_contracts_envelopes_takes_the_whole_tree` — Deleting a contracts envelopes takes the whole tree

</details>


#### BB-06

**UAT-BB-06-01** · Run the visitor esign suite

*Why it matters:* Visitor eSigning — the public, unauthenticated surface.

*Automated by:* `test_visitor_esign.py` — 40 tests

<details><summary>Tests in this script</summary>

- `test_security_module_import_is_not_needed` — Security module import is not needed
- `test_only_a_hash_of_the_token_is_stored` — Only a hash of the token is stored
- `test_token_copy_is_encrypted_at_rest` — Token copy is encrypted at rest
- `test_token_resolves` — Token resolves
- `test_wrong_token_does_not_resolve` — Wrong token does not resolve
- `test_expired_invitation_does_not_resolve` — Expired invitation does not resolve
- `test_revoked_invitation_does_not_resolve` — Revoked invitation does not resolve
- `test_use_cap_closes_the_link` — Use cap closes the link
- `test_start_sends_a_masked_code_and_creates_nothing_irreversible` — Start sends a masked code and creates nothing irreversible
- `test_wrong_code_is_rejected` — Wrong code is rejected
- `test_brute_force_is_blocked` — Brute force is blocked
- `test_expired_code_is_rejected` — Expired code is rejected
- `test_correct_code_verifies_and_burns_the_code` — Correct code verifies and burns the code
- `test_resend_is_capped` — Resend is capped
- `test_session_from_another_invitation_is_not_accepted` — Session from another invitation is not accepted
- `test_sms_channel_requires_a_number` — Sms channel requires a number
- `test_cnic_is_reduced_to_the_last_four_digits` — CNIC is reduced to the last four digits
- `test_rate_limited_per_ip` — Rate limited per ip
- `test_same_identifier_yields_the_same_party` — Same identifier yields the same party
- `test_party_ref_does_not_contain_the_identifier` — Party ref does not contain the identifier
- `test_phone_spellings_normalise_to_one_party` — Phone spellings normalise to one party
- `test_normalisation` — Normalisation
- `test_masking_keeps_only_the_last_four` — Masking keeps only the last four
- `test_signing_is_locked_until_the_document_is_read` — Signing is locked until the document is read
- `test_unverified_session_can_never_sign` — Unverified session can never sign
- `test_evidence_bundle_is_masked` — Evidence bundle is masked
- `test_verified_visitor_gets_their_own_short_lived_certificate` — Verified visitor gets their own short lived certificate
- `test_certificate_records_that_it_was_auto_approved` — Certificate records that it was auto approved
- `test_returning_visitor_reuses_their_certificate` — Returning visitor reuses their certificate
- `test_unverified_session_cannot_get_a_certificate` — Unverified session cannot get a certificate
- `test_missing_pki_does_not_block_signing` — Missing PKI does not block signing
- `test_valid_solution_is_accepted` — Valid solution is accepted
- `test_wrong_solution_is_rejected` — Wrong solution is rejected
- `test_forged_challenge_is_rejected` — Forged challenge is rejected
- `test_challenge_is_bound_to_the_invitation` — Challenge is bound to the invitation
- `test_disabled_when_bits_is_zero` — Disabled when bits is zero
- `test_verified_visitor_joins_the_live_envelope` — Verified visitor joins the live envelope
- `test_no_open_envelope_is_a_clear_error` — No open envelope is a clear error
- `test_reattaching_returns_the_same_recipient` — Reattaching returns the same recipient
- `test_sms_rows_are_marked_and_excluded_from_the_smtp_flush` — Sms rows are marked and excluded from the smtp flush

</details>



### Technical Requirements — RFP §4b / §4c

#### TEC-04

**UAT-TEC-04-01** · Run the db dialect suite

*Why it matters:* The dialect seam (`app/db_dialect.py`) generates the DDL that enforces tenant isolation on each supported engine. These are pure string tests — no database needed — because the property that matters is *semantic equivalence across dialects*, and getting that wrong on an engine we cannot spin up locally is exactly the failure mode this module exists to prevent.

*Automated by:* `test_db_dialect.py` — 11 tests

<details><summary>Tests in this script</summary>

- `test_row_security_covers_every_table` — Row security covers every table
- `test_row_security_is_permissive_when_tenant_unset` — Row security is permissive when tenant unset
- `test_row_security_blocks_writes_not_just_reads` — Row security blocks writes not just reads
- `test_oracle_predicate_quotes_survive_plsql` — Oracle predicate quotes survive plsql
- `test_sqlite_gets_no_row_security` — Sqlite gets no row security
- `test_disable_row_security_is_the_inverse` — Disable row security is the inverse
- `test_json_index_never_lies` — Json index never lies
- `test_json_index_uses_supplied_name` — Json index uses supplied name
- `test_json_check_constrains_untyped_json_columns` — Json check constrains untyped json columns
- `test_fulltext_search_binds_the_query_parameter` — Fulltext search binds the query parameter
- `test_fulltext_search_degrades_to_like_on_sqlite` — Fulltext search degrades to like on sqlite

</details>


#### TEC-06

**UAT-TEC-06-01** · Run the archive retention suite

*Why it matters:* Archive and purge — the 10-year retention tier with a 1-year hot search window.

*Automated by:* `test_archive_retention.py` — 12 tests

<details><summary>Tests in this script</summary>

- `test_archives_contract_past_the_hot_window` — Archives contract past the hot window
- `test_leaves_contracts_inside_the_hot_window_alone` — Leaves contracts inside the hot window alone
- `test_legal_hold_blocks_archival` — Legal hold blocks archival
- `test_drafts_are_never_archived` — Drafts are never archived
- `test_archive_is_idempotent` — Archive is idempotent
- `test_archive_writes_an_audit_entry` — Archive writes an audit entry
- `test_archived_files_move_to_the_cold_prefix` — Archived files move to the cold prefix
- `test_purges_contract_past_retention` — Purges contract past retention
- `test_does_not_purge_inside_retention` — Does not purge inside retention
- `test_legal_hold_blocks_purge` — Legal hold blocks purge
- `test_purge_removes_children_and_records_evidence` — Purge removes children and records evidence
- `test_eligibility_gate_is_shared_by_both_sweeps` — Eligibility gate is shared by both sweeps

</details>


#### TEC-08

**UAT-TEC-08-01** · Run the worker metrics suite

*Why it matters:* Worker-side Prometheus metrics (Phase 10).

*Automated by:* `test_worker_metrics.py` — 14 tests

<details><summary>Tests in this script</summary>

- `test_a_successful_task_is_counted_by_name` — A successful task is counted by name
- `test_a_failed_task_is_counted_separately` — A failed task is counted separately
- `test_retries_and_revocations_are_distinguishable` — Retries and revocations are distinguishable
- `test_a_task_with_no_name_is_labelled_rather_than_dropped` — A task with no name is labelled rather than dropped
- `test_a_task_run_records_its_duration_and_clears_in_flight` — A task run records its duration and clears in flight
- `test_in_flight_returns_to_zero_even_when_a_task_fails` — In flight returns to zero even when a task fails
- `test_a_postrun_without_a_matching_prerun_does_not_raise` — A postrun without a matching prerun does not raise
- `test_a_sweeps_returned_counts_become_metrics` — A sweeps returned counts become metrics
- `test_a_non_dict_result_contributes_nothing` — A non dict result contributes nothing
- `test_non_integer_values_in_a_result_are_skipped` — Non integer values in a result are skipped
- `test_record_sweep_never_raises` — Record sweep never raises
- `test_the_worker_reports_up_and_down` — The worker reports up and down
- `test_the_exporter_can_be_switched_off` — The exporter can be switched off
- `test_a_failure_to_bind_does_not_stop_the_worker` — A failure to bind does not stop the worker

</details>



### Information Security — RFP §4d

#### SEC-01

**UAT-SEC-01-01** · Run the access control suite

*Why it matters:* Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

*Automated by:* `test_access_control.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_builtin_roles_carry_what_they_should` — The builtin roles carry what they should
- `test_an_unknown_role_degrades_to_viewer_not_to_nothing` — An unknown role degrades to viewer not to nothing
- `test_a_custom_role_extends_its_base` — A custom role extends its base
- `test_a_revoke_always_wins` — A revoke always wins
- `test_an_inactive_custom_role_falls_back` — An inactive custom role falls back
- `test_require_raises_rather_than_returning_false` — Require raises rather than returning false
- `test_the_author_of_an_agreement_cannot_approve_it` — The author of an agreement cannot approve it
- `test_somebody_else_can_approve_it` — Somebody else can approve it
- `test_the_rule_is_per_object_not_global` — The rule is per object not global
- `test_a_block_is_recorded` — A block is recorded
- `test_an_override_needs_a_reason_and_is_audited_loudly` — An override needs a reason and is audited loudly
- `test_a_webhook_creator_cannot_reveal_its_own_secret` — A webhook creator cannot reveal its own secret
- `test_an_unrelated_action_is_not_segregated` — An unrelated action is not segregated
- `test_only_sensitive_actions_need_step_up` — Only sensitive actions need step up
- `test_a_sensitive_action_without_a_challenge_demands_one` — A sensitive action without a challenge demands one
- `test_a_satisfied_challenge_lets_the_action_through` — A satisfied challenge lets the action through
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_a_challenge_cannot_be_replayed_against_another_object` — A challenge cannot be replayed against another object
- `test_a_challenge_cannot_be_reused_for_a_different_action` — A challenge cannot be reused for a different action
- `test_a_wrong_password_does_not_satisfy_a_challenge` — A wrong password does not satisfy a challenge
- `test_repeated_wrong_answers_burn_the_challenge` — Repeated wrong answers burn the challenge
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_somebody_elses_challenge_cannot_be_answered` — Somebody elses challenge cannot be answered
- `test_an_ordinary_agreement_is_visible_to_everyone` — An ordinary agreement is visible to everyone
- `test_a_confidential_agreement_is_not` — A confidential agreement is not
- `test_the_owner_can_always_see_their_own` — The owner can always see their own
- `test_an_explicit_grant_opens_it` — An explicit grant opens it
- `test_a_role_grant_opens_it_for_that_role` — A role grant opens it for that role
- `test_an_expired_grant_closes_again` — An expired grant closes again
- `test_a_refused_read_is_logged` — A refused read is logged
- `test_break_glass_needs_a_reason` — Break glass needs a reason
- `test_break_glass_grants_access_and_shouts_about_it` — Break glass grants access and shouts about it
- `test_a_link_resolves_to_its_record` — A link resolves to its record
- `test_only_the_hash_is_stored` — Only the hash is stored
- `test_a_revoked_link_stops_resolving` — A revoked link stops resolving
- `test_an_expired_link_stops_resolving` — An expired link stops resolving
- `test_a_wrong_token_resolves_to_nothing` — A wrong token resolves to nothing
- `test_an_absurd_duration_is_refused` — An absurd duration is refused
- `test_the_expiry_sweep_is_idempotent` — The expiry sweep is idempotent
- `test_placing_a_hold_sets_the_flag_every_retention_path_reads` — Placing a hold sets the flag every retention path reads
- `test_a_hold_needs_a_matter_and_something_to_hold` — A hold needs a matter and something to hold
- `test_a_hold_over_a_missing_agreement_is_refused` — A hold over a missing agreement is refused
- `test_releasing_needs_a_reason` — Releasing needs a reason
- `test_releasing_the_only_hold_clears_the_flag` — Releasing the only hold clears the flag
- `test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers` — Releasing one matter does not expose an agreement another still covers
- `test_a_released_hold_cannot_be_released_twice` — A released hold cannot be released twice
- `test_extending_a_hold_covers_the_new_agreements` — Extending a hold covers the new agreements
- `test_the_export_set_carries_audit_chain_positions` — The export set carries audit chain positions
- `test_reconcile_repairs_a_drifted_flag` — Reconcile repairs a drifted flag

</details>


#### SEC-02

**UAT-SEC-02-01** · Run the auth service suite

*Why it matters:* Session, MFA and lockout mechanics (Phase 10 — coverage on `auth_service`).

*Automated by:* `test_auth_service.py` — 36 tests

<details><summary>Tests in this script</summary>

- `test_a_new_session_starts_its_own_chain` — A new session starts its own chain
- `test_rotation_links_to_the_parent_and_keeps_the_chain` — Rotation links to the parent and keeps the chain
- `test_an_unknown_token_is_invalid_not_an_error` — An unknown token is invalid not an error
- `test_an_expired_session_is_marked_expired_not_reused` — An expired session is marked expired not reused
- `test_a_deliberately_revoked_session_is_not_treated_as_theft` — A deliberately revoked session is not treated as theft
- `test_replaying_a_rotated_token_burns_the_whole_chain` — Replaying a rotated token burns the whole chain
- `test_revoking_by_id_reports_whether_anything_happened` — Revoking by id reports whether anything happened
- `test_signing_out_everywhere_can_spare_the_current_device` — Signing out everywhere can spare the current device
- `test_active_sessions_exclude_revoked_and_expired` — Active sessions exclude revoked and expired
- `test_revoking_a_chain_leaves_other_chains_alone` — Revoking a chain leaves other chains alone
- `test_a_current_totp_code_verifies` — A current totp code verifies
- `test_totp_tolerates_a_space_and_surrounding_whitespace` — Totp tolerates a space and surrounding whitespace
- `test_totp_without_a_secret_is_false_not_an_exception` — Totp without a secret is false not an exception
- `test_a_malformed_secret_does_not_raise` — A malformed secret does not raise
- `test_the_provisioning_uri_names_the_account_and_issuer` — The provisioning uri names the account and issuer
- `test_recovery_codes_are_stored_hashed` — Recovery codes are stored hashed
- `test_a_recovery_code_works_exactly_once` — A recovery code works exactly once
- `test_recovery_codes_are_normalised_before_matching` — Recovery codes are normalised before matching
- `test_regenerating_invalidates_the_previous_set` — Regenerating invalidates the previous set
- `test_another_users_recovery_code_does_not_work` — Another users recovery code does not work
- `test_an_issued_otp_verifies_once` — An issued OTP verifies once
- `test_issuing_a_new_otp_kills_the_previous_one` — Issuing a new OTP kills the previous one
- `test_an_expired_otp_is_refused_and_spent` — An expired OTP is refused and spent
- `test_too_many_wrong_guesses_burns_the_otp` — Too many wrong guesses burns the OTP
- `test_an_otp_for_another_purpose_does_not_unlock_this_one` — An OTP for another purpose does not unlock this one
- `test_verifying_with_no_outstanding_code_is_false` — Verifying with no outstanding code is false
- `test_repeated_failures_lock_the_account` — Repeated failures lock the account
- `test_a_failure_for_an_unknown_email_is_logged_without_a_lockout` — A failure for an unknown email is logged without a lockout
- `test_the_failure_window_rolls_over` — The failure window rolls over
- `test_an_expired_lockout_clears_itself` — An expired lockout clears itself
- `test_a_successful_login_resets_the_counter` — A successful login resets the counter
- `test_an_admin_can_release_a_lockout` — An admin can release a lockout
- `test_a_user_who_never_failed_is_not_locked_out` — A user who never failed is not locked out
- `test_admin_reset_on_a_clean_account_is_a_no_op` — Admin reset on a clean account is a no op
- `test_reuse_detection_is_written_to_the_audit_log` — Reuse detection is written to the audit log
- `test_reuse_is_escalated_for_the_siem` — Reuse is escalated for the SIEM

</details>


#### SEC-03

**UAT-SEC-03-01** · Run the webauthn suite

*Why it matters:* FIDO2 / WebAuthn (Phase 8, item 1).

*Automated by:* `test_webauthn.py` — 17 tests

<details><summary>Tests in this script</summary>

- `test_registration_stores_only_a_public_key` — Registration stores only a public key
- `test_registration_is_audited` — Registration is audited
- `test_a_tampered_attestation_is_refused` — A tampered attestation is refused
- `test_the_same_key_cannot_enrol_twice` — The same key cannot enrol twice
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_disabled_when_not_configured` — Disabled when not configured
- `test_a_real_assertion_verifies` — A real assertion verifies
- `test_a_forged_signature_does_not_verify` — A forged signature does not verify
- `test_a_counter_that_does_not_advance_is_refused` — A counter that does not advance is refused
- `test_a_failed_assertion_is_audited` — A failed assertion is audited
- `test_another_users_passkey_is_not_accepted` — Another users passkey is not accepted
- `test_authentication_without_a_passkey_says_so` — Authentication without a passkey says so
- `test_removing_a_passkey_is_audited` — Removing a passkey is audited
- `test_the_last_factor_cannot_be_removed` — The last factor cannot be removed
- `test_another_users_passkey_cannot_be_removed` — Another users passkey cannot be removed
- `test_status_reports_the_fallback_honestly` — Status reports the fallback honestly

</details>


#### SEC-04

**UAT-SEC-04-01** · Run the saml suite

*Why it matters:* SAML 2.0 service provider.

*Automated by:* `test_saml.py` — 30 tests

<details><summary>Tests in this script</summary>

- `test_saml_is_off_until_configured` — Saml is off until configured
- `test_enabling_without_a_certificate_is_still_off` — Enabling without a certificate is still off
- `test_metadata_names_the_real_endpoints` — Metadata names the real endpoints
- `test_a_bare_base64_certificate_is_accepted` — A bare base64 certificate is accepted
- `test_the_authn_request_is_deflated_and_encoded` — The authn request is deflated and encoded
- `test_relay_state_is_carried_through` — Relay state is carried through
- `test_a_properly_signed_assertion_is_accepted` — A properly signed assertion is accepted
- `test_an_unsigned_assertion_is_rejected` — An unsigned assertion is rejected
- `test_an_assertion_signed_by_another_idp_is_rejected` — An assertion signed by another idp is rejected
- `test_a_tampered_assertion_is_rejected` — A tampered assertion is rejected
- `test_an_assertion_for_another_service_is_rejected` — An assertion for another service is rejected
- `test_an_expired_assertion_is_rejected` — An expired assertion is rejected
- `test_an_assertion_from_the_future_is_rejected` — An assertion from the future is rejected
- `test_small_clock_skew_is_tolerated` — Small clock skew is tolerated
- `test_an_assertion_cannot_be_replayed` — An assertion cannot be replayed
- `test_a_response_answering_a_different_request_is_rejected` — A response answering a different request is rejected
- `test_a_response_matching_our_request_is_accepted` — A response matching our request is accepted
- `test_an_assertion_addressed_elsewhere_is_rejected` — An assertion addressed elsewhere is rejected
- `test_an_idp_initiated_assertion_is_accepted` — An idp initiated assertion is accepted
- `test_an_assertion_without_an_email_is_rejected` — An assertion without an email is rejected
- `test_rubbish_is_rejected_without_exploding` — Rubbish is rejected without exploding
- `test_a_mapped_group_selects_the_role` — A mapped group selects the role
- `test_an_unmapped_group_falls_back_to_the_default_role` — An unmapped group falls back to the default role
- `test_no_groups_at_all_still_gets_the_default_role` — No groups at all still gets the default role
- `test_logout_redirects_to_the_idp_when_it_has_an_slo_endpoint` — Logout redirects to the idp when it has an slo endpoint
- `test_logout_falls_back_locally_when_the_idp_has_no_slo` — Logout falls back locally when the idp has no slo
- `test_the_endpoints_are_absent_until_saml_is_configured` — The endpoints are absent until saml is configured
- `test_metadata_is_served_as_xml` — Metadata is served as xml
- `test_login_redirects_to_the_idp` — Login redirects to the idp
- `test_a_rejected_assertion_does_not_explain_itself_to_the_browser` — A rejected assertion does not explain itself to the browser

</details>


#### SEC-06

**UAT-SEC-06-01** · Run the auth service suite

*Why it matters:* Session, MFA and lockout mechanics (Phase 10 — coverage on `auth_service`).

*Automated by:* `test_auth_service.py` — 36 tests

<details><summary>Tests in this script</summary>

- `test_a_new_session_starts_its_own_chain` — A new session starts its own chain
- `test_rotation_links_to_the_parent_and_keeps_the_chain` — Rotation links to the parent and keeps the chain
- `test_an_unknown_token_is_invalid_not_an_error` — An unknown token is invalid not an error
- `test_an_expired_session_is_marked_expired_not_reused` — An expired session is marked expired not reused
- `test_a_deliberately_revoked_session_is_not_treated_as_theft` — A deliberately revoked session is not treated as theft
- `test_replaying_a_rotated_token_burns_the_whole_chain` — Replaying a rotated token burns the whole chain
- `test_revoking_by_id_reports_whether_anything_happened` — Revoking by id reports whether anything happened
- `test_signing_out_everywhere_can_spare_the_current_device` — Signing out everywhere can spare the current device
- `test_active_sessions_exclude_revoked_and_expired` — Active sessions exclude revoked and expired
- `test_revoking_a_chain_leaves_other_chains_alone` — Revoking a chain leaves other chains alone
- `test_a_current_totp_code_verifies` — A current totp code verifies
- `test_totp_tolerates_a_space_and_surrounding_whitespace` — Totp tolerates a space and surrounding whitespace
- `test_totp_without_a_secret_is_false_not_an_exception` — Totp without a secret is false not an exception
- `test_a_malformed_secret_does_not_raise` — A malformed secret does not raise
- `test_the_provisioning_uri_names_the_account_and_issuer` — The provisioning uri names the account and issuer
- `test_recovery_codes_are_stored_hashed` — Recovery codes are stored hashed
- `test_a_recovery_code_works_exactly_once` — A recovery code works exactly once
- `test_recovery_codes_are_normalised_before_matching` — Recovery codes are normalised before matching
- `test_regenerating_invalidates_the_previous_set` — Regenerating invalidates the previous set
- `test_another_users_recovery_code_does_not_work` — Another users recovery code does not work
- `test_an_issued_otp_verifies_once` — An issued OTP verifies once
- `test_issuing_a_new_otp_kills_the_previous_one` — Issuing a new OTP kills the previous one
- `test_an_expired_otp_is_refused_and_spent` — An expired OTP is refused and spent
- `test_too_many_wrong_guesses_burns_the_otp` — Too many wrong guesses burns the OTP
- `test_an_otp_for_another_purpose_does_not_unlock_this_one` — An OTP for another purpose does not unlock this one
- `test_verifying_with_no_outstanding_code_is_false` — Verifying with no outstanding code is false
- `test_repeated_failures_lock_the_account` — Repeated failures lock the account
- `test_a_failure_for_an_unknown_email_is_logged_without_a_lockout` — A failure for an unknown email is logged without a lockout
- `test_the_failure_window_rolls_over` — The failure window rolls over
- `test_an_expired_lockout_clears_itself` — An expired lockout clears itself
- `test_a_successful_login_resets_the_counter` — A successful login resets the counter
- `test_an_admin_can_release_a_lockout` — An admin can release a lockout
- `test_a_user_who_never_failed_is_not_locked_out` — A user who never failed is not locked out
- `test_admin_reset_on_a_clean_account_is_a_no_op` — Admin reset on a clean account is a no op
- `test_reuse_detection_is_written_to_the_audit_log` — Reuse detection is written to the audit log
- `test_reuse_is_escalated_for_the_siem` — Reuse is escalated for the SIEM

</details>

**UAT-SEC-06-02** · Run the lifecycle and refresh suite

*Why it matters:* Lifecycle invariants + refresh-token reuse detection.

*Automated by:* `test_lifecycle_and_refresh.py` — 7 tests

<details><summary>Tests in this script</summary>

- `test_legal_transitions_match_transitions_dict` — Legal transitions match transitions dict
- `test_signed_is_a_sink_apart_from_active` — Signed is a sink apart from active
- `test_void_and_terminate_are_final` — Void and terminate are final
- `test_expired_is_not_terminal_because_an_expired_agreement_can_be_renewed` — Expired is not terminal because an expired agreement can be renewed
- `test_declined_returns_to_draft_rather_than_dying` — Declined returns to draft rather than dying
- `test_reused_rotated_token_burns_the_chain` — Reused rotated token burns the chain
- `test_legitimate_rotation_does_not_burn_chain` — Legitimate rotation does not burn chain

</details>


#### SEC-07

**UAT-SEC-07-01** · Run the access control suite

*Why it matters:* Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

*Automated by:* `test_access_control.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_builtin_roles_carry_what_they_should` — The builtin roles carry what they should
- `test_an_unknown_role_degrades_to_viewer_not_to_nothing` — An unknown role degrades to viewer not to nothing
- `test_a_custom_role_extends_its_base` — A custom role extends its base
- `test_a_revoke_always_wins` — A revoke always wins
- `test_an_inactive_custom_role_falls_back` — An inactive custom role falls back
- `test_require_raises_rather_than_returning_false` — Require raises rather than returning false
- `test_the_author_of_an_agreement_cannot_approve_it` — The author of an agreement cannot approve it
- `test_somebody_else_can_approve_it` — Somebody else can approve it
- `test_the_rule_is_per_object_not_global` — The rule is per object not global
- `test_a_block_is_recorded` — A block is recorded
- `test_an_override_needs_a_reason_and_is_audited_loudly` — An override needs a reason and is audited loudly
- `test_a_webhook_creator_cannot_reveal_its_own_secret` — A webhook creator cannot reveal its own secret
- `test_an_unrelated_action_is_not_segregated` — An unrelated action is not segregated
- `test_only_sensitive_actions_need_step_up` — Only sensitive actions need step up
- `test_a_sensitive_action_without_a_challenge_demands_one` — A sensitive action without a challenge demands one
- `test_a_satisfied_challenge_lets_the_action_through` — A satisfied challenge lets the action through
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_a_challenge_cannot_be_replayed_against_another_object` — A challenge cannot be replayed against another object
- `test_a_challenge_cannot_be_reused_for_a_different_action` — A challenge cannot be reused for a different action
- `test_a_wrong_password_does_not_satisfy_a_challenge` — A wrong password does not satisfy a challenge
- `test_repeated_wrong_answers_burn_the_challenge` — Repeated wrong answers burn the challenge
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_somebody_elses_challenge_cannot_be_answered` — Somebody elses challenge cannot be answered
- `test_an_ordinary_agreement_is_visible_to_everyone` — An ordinary agreement is visible to everyone
- `test_a_confidential_agreement_is_not` — A confidential agreement is not
- `test_the_owner_can_always_see_their_own` — The owner can always see their own
- `test_an_explicit_grant_opens_it` — An explicit grant opens it
- `test_a_role_grant_opens_it_for_that_role` — A role grant opens it for that role
- `test_an_expired_grant_closes_again` — An expired grant closes again
- `test_a_refused_read_is_logged` — A refused read is logged
- `test_break_glass_needs_a_reason` — Break glass needs a reason
- `test_break_glass_grants_access_and_shouts_about_it` — Break glass grants access and shouts about it
- `test_a_link_resolves_to_its_record` — A link resolves to its record
- `test_only_the_hash_is_stored` — Only the hash is stored
- `test_a_revoked_link_stops_resolving` — A revoked link stops resolving
- `test_an_expired_link_stops_resolving` — An expired link stops resolving
- `test_a_wrong_token_resolves_to_nothing` — A wrong token resolves to nothing
- `test_an_absurd_duration_is_refused` — An absurd duration is refused
- `test_the_expiry_sweep_is_idempotent` — The expiry sweep is idempotent
- `test_placing_a_hold_sets_the_flag_every_retention_path_reads` — Placing a hold sets the flag every retention path reads
- `test_a_hold_needs_a_matter_and_something_to_hold` — A hold needs a matter and something to hold
- `test_a_hold_over_a_missing_agreement_is_refused` — A hold over a missing agreement is refused
- `test_releasing_needs_a_reason` — Releasing needs a reason
- `test_releasing_the_only_hold_clears_the_flag` — Releasing the only hold clears the flag
- `test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers` — Releasing one matter does not expose an agreement another still covers
- `test_a_released_hold_cannot_be_released_twice` — A released hold cannot be released twice
- `test_extending_a_hold_covers_the_new_agreements` — Extending a hold covers the new agreements
- `test_the_export_set_carries_audit_chain_positions` — The export set carries audit chain positions
- `test_reconcile_repairs_a_drifted_flag` — Reconcile repairs a drifted flag

</details>


#### SEC-08

**UAT-SEC-08-01** · Run the access control suite

*Why it matters:* Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

*Automated by:* `test_access_control.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_builtin_roles_carry_what_they_should` — The builtin roles carry what they should
- `test_an_unknown_role_degrades_to_viewer_not_to_nothing` — An unknown role degrades to viewer not to nothing
- `test_a_custom_role_extends_its_base` — A custom role extends its base
- `test_a_revoke_always_wins` — A revoke always wins
- `test_an_inactive_custom_role_falls_back` — An inactive custom role falls back
- `test_require_raises_rather_than_returning_false` — Require raises rather than returning false
- `test_the_author_of_an_agreement_cannot_approve_it` — The author of an agreement cannot approve it
- `test_somebody_else_can_approve_it` — Somebody else can approve it
- `test_the_rule_is_per_object_not_global` — The rule is per object not global
- `test_a_block_is_recorded` — A block is recorded
- `test_an_override_needs_a_reason_and_is_audited_loudly` — An override needs a reason and is audited loudly
- `test_a_webhook_creator_cannot_reveal_its_own_secret` — A webhook creator cannot reveal its own secret
- `test_an_unrelated_action_is_not_segregated` — An unrelated action is not segregated
- `test_only_sensitive_actions_need_step_up` — Only sensitive actions need step up
- `test_a_sensitive_action_without_a_challenge_demands_one` — A sensitive action without a challenge demands one
- `test_a_satisfied_challenge_lets_the_action_through` — A satisfied challenge lets the action through
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_a_challenge_cannot_be_replayed_against_another_object` — A challenge cannot be replayed against another object
- `test_a_challenge_cannot_be_reused_for_a_different_action` — A challenge cannot be reused for a different action
- `test_a_wrong_password_does_not_satisfy_a_challenge` — A wrong password does not satisfy a challenge
- `test_repeated_wrong_answers_burn_the_challenge` — Repeated wrong answers burn the challenge
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_somebody_elses_challenge_cannot_be_answered` — Somebody elses challenge cannot be answered
- `test_an_ordinary_agreement_is_visible_to_everyone` — An ordinary agreement is visible to everyone
- `test_a_confidential_agreement_is_not` — A confidential agreement is not
- `test_the_owner_can_always_see_their_own` — The owner can always see their own
- `test_an_explicit_grant_opens_it` — An explicit grant opens it
- `test_a_role_grant_opens_it_for_that_role` — A role grant opens it for that role
- `test_an_expired_grant_closes_again` — An expired grant closes again
- `test_a_refused_read_is_logged` — A refused read is logged
- `test_break_glass_needs_a_reason` — Break glass needs a reason
- `test_break_glass_grants_access_and_shouts_about_it` — Break glass grants access and shouts about it
- `test_a_link_resolves_to_its_record` — A link resolves to its record
- `test_only_the_hash_is_stored` — Only the hash is stored
- `test_a_revoked_link_stops_resolving` — A revoked link stops resolving
- `test_an_expired_link_stops_resolving` — An expired link stops resolving
- `test_a_wrong_token_resolves_to_nothing` — A wrong token resolves to nothing
- `test_an_absurd_duration_is_refused` — An absurd duration is refused
- `test_the_expiry_sweep_is_idempotent` — The expiry sweep is idempotent
- `test_placing_a_hold_sets_the_flag_every_retention_path_reads` — Placing a hold sets the flag every retention path reads
- `test_a_hold_needs_a_matter_and_something_to_hold` — A hold needs a matter and something to hold
- `test_a_hold_over_a_missing_agreement_is_refused` — A hold over a missing agreement is refused
- `test_releasing_needs_a_reason` — Releasing needs a reason
- `test_releasing_the_only_hold_clears_the_flag` — Releasing the only hold clears the flag
- `test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers` — Releasing one matter does not expose an agreement another still covers
- `test_a_released_hold_cannot_be_released_twice` — A released hold cannot be released twice
- `test_extending_a_hold_covers_the_new_agreements` — Extending a hold covers the new agreements
- `test_the_export_set_carries_audit_chain_positions` — The export set carries audit chain positions
- `test_reconcile_repairs_a_drifted_flag` — Reconcile repairs a drifted flag

</details>


#### SEC-09

**UAT-SEC-09-01** · Run the access control suite

*Why it matters:* Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

*Automated by:* `test_access_control.py` — 49 tests

<details><summary>Tests in this script</summary>

- `test_the_builtin_roles_carry_what_they_should` — The builtin roles carry what they should
- `test_an_unknown_role_degrades_to_viewer_not_to_nothing` — An unknown role degrades to viewer not to nothing
- `test_a_custom_role_extends_its_base` — A custom role extends its base
- `test_a_revoke_always_wins` — A revoke always wins
- `test_an_inactive_custom_role_falls_back` — An inactive custom role falls back
- `test_require_raises_rather_than_returning_false` — Require raises rather than returning false
- `test_the_author_of_an_agreement_cannot_approve_it` — The author of an agreement cannot approve it
- `test_somebody_else_can_approve_it` — Somebody else can approve it
- `test_the_rule_is_per_object_not_global` — The rule is per object not global
- `test_a_block_is_recorded` — A block is recorded
- `test_an_override_needs_a_reason_and_is_audited_loudly` — An override needs a reason and is audited loudly
- `test_a_webhook_creator_cannot_reveal_its_own_secret` — A webhook creator cannot reveal its own secret
- `test_an_unrelated_action_is_not_segregated` — An unrelated action is not segregated
- `test_only_sensitive_actions_need_step_up` — Only sensitive actions need step up
- `test_a_sensitive_action_without_a_challenge_demands_one` — A sensitive action without a challenge demands one
- `test_a_satisfied_challenge_lets_the_action_through` — A satisfied challenge lets the action through
- `test_a_challenge_is_single_use` — A challenge is single use
- `test_a_challenge_cannot_be_replayed_against_another_object` — A challenge cannot be replayed against another object
- `test_a_challenge_cannot_be_reused_for_a_different_action` — A challenge cannot be reused for a different action
- `test_a_wrong_password_does_not_satisfy_a_challenge` — A wrong password does not satisfy a challenge
- `test_repeated_wrong_answers_burn_the_challenge` — Repeated wrong answers burn the challenge
- `test_an_expired_challenge_is_refused` — An expired challenge is refused
- `test_somebody_elses_challenge_cannot_be_answered` — Somebody elses challenge cannot be answered
- `test_an_ordinary_agreement_is_visible_to_everyone` — An ordinary agreement is visible to everyone
- `test_a_confidential_agreement_is_not` — A confidential agreement is not
- `test_the_owner_can_always_see_their_own` — The owner can always see their own
- `test_an_explicit_grant_opens_it` — An explicit grant opens it
- `test_a_role_grant_opens_it_for_that_role` — A role grant opens it for that role
- `test_an_expired_grant_closes_again` — An expired grant closes again
- `test_a_refused_read_is_logged` — A refused read is logged
- `test_break_glass_needs_a_reason` — Break glass needs a reason
- `test_break_glass_grants_access_and_shouts_about_it` — Break glass grants access and shouts about it
- `test_a_link_resolves_to_its_record` — A link resolves to its record
- `test_only_the_hash_is_stored` — Only the hash is stored
- `test_a_revoked_link_stops_resolving` — A revoked link stops resolving
- `test_an_expired_link_stops_resolving` — An expired link stops resolving
- `test_a_wrong_token_resolves_to_nothing` — A wrong token resolves to nothing
- `test_an_absurd_duration_is_refused` — An absurd duration is refused
- `test_the_expiry_sweep_is_idempotent` — The expiry sweep is idempotent
- `test_placing_a_hold_sets_the_flag_every_retention_path_reads` — Placing a hold sets the flag every retention path reads
- `test_a_hold_needs_a_matter_and_something_to_hold` — A hold needs a matter and something to hold
- `test_a_hold_over_a_missing_agreement_is_refused` — A hold over a missing agreement is refused
- `test_releasing_needs_a_reason` — Releasing needs a reason
- `test_releasing_the_only_hold_clears_the_flag` — Releasing the only hold clears the flag
- `test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers` — Releasing one matter does not expose an agreement another still covers
- `test_a_released_hold_cannot_be_released_twice` — A released hold cannot be released twice
- `test_extending_a_hold_covers_the_new_agreements` — Extending a hold covers the new agreements
- `test_the_export_set_carries_audit_chain_positions` — The export set carries audit chain positions
- `test_reconcile_repairs_a_drifted_flag` — Reconcile repairs a drifted flag

</details>


#### SEC-12

**UAT-SEC-12-01** · Run the audit chain suite

*Why it matters:* Audit-log tamper-evidence chain — verifies that every audit row is HMAC-linked, that verification detects deletions and in-place edits, and that pre-chain rows are ignored.

*Automated by:* `test_audit_chain.py` — 9 tests

<details><summary>Tests in this script</summary>

- `test_two_entries_in_one_transaction_chain_correctly` — Two entries in one transaction chain correctly
- `test_each_row_chains_to_the_previous` — Each row chains to the previous
- `test_verify_chain_is_ok_on_clean_data` — Verify chain is ok on clean data
- `test_verify_detects_in_place_edit` — Verify detects in place edit
- `test_verify_detects_row_deletion` — Verify detects row deletion
- `test_chain_is_per_tenant` — Chain is per tenant
- `test_rows_in_the_same_tick_still_chain_in_insertion_order` — Rows in the same tick still chain in insertion order
- `test_deleting_a_row_written_in_a_tied_tick_is_still_detected` — Deleting a row written in a tied tick is still detected
- `test_an_edit_in_a_tied_tick_is_still_detected` — An edit in a tied tick is still detected

</details>


#### SEC-13

**UAT-SEC-13-01** · Run the integrations suite

*Why it matters:* SIEM feed and sanctions screening.

*Automated by:* `test_integrations.py` — 65 tests

<details><summary>Tests in this script</summary>

- `test_actions_land_in_the_right_siem_category` — Actions land in the right SIEM category
- `test_a_failed_login_outranks_a_successful_one` — A failed login outranks a successful one
- `test_a_broken_audit_chain_is_critical` — A broken audit chain is critical
- `test_an_unknown_action_is_still_reported` — An unknown action is still reported
- `test_cef_has_the_required_header_fields` — CEF has the required header fields
- `test_cef_severity_runs_the_opposite_way_to_syslog` — CEF severity runs the opposite way to syslog
- `test_cef_carries_the_actor_ip_and_chain_position` — CEF carries the actor ip and chain position
- `test_cef_escapes_a_pipe_in_the_header` — CEF escapes a pipe in the header
- `test_cef_escapes_an_equals_sign_in_the_extension` — CEF escapes an equals sign in the extension
- `test_clf_is_a_parseable_web_log_line` — Clf is a parseable web log line
- `test_the_syslog_frame_is_octet_counted` — The syslog frame is octet counted
- `test_the_syslog_priority_encodes_the_severity` — The syslog priority encodes the severity
- `test_the_feed_is_off_until_configured` — The feed is off until configured
- `test_emitting_while_disabled_is_a_no_op` — Emitting while disabled is a no op
- `test_events_reach_a_listening_collector` — Events reach a listening collector
- `test_an_unreachable_collector_does_not_raise` — An unreachable collector does not raise
- `test_a_batch_reports_what_got_through` — A batch reports what got through
- `test_transliterations_and_reorderings_still_match` — Transliterations and reorderings still match
- `test_different_people_do_not_match` — Different people do not match
- `test_a_single_shared_common_name_is_not_a_match` — A single shared common name is not a match
- `test_a_shorter_name_inside_a_longer_one_matches` — A shorter name inside a longer one matches
- `test_normalisation_drops_entity_noise` — Normalisation drops entity noise
- `test_a_clean_screen_is_still_recorded` — A clean screen is still recorded
- `test_a_match_raises_a_review_rather_than_rejecting` — A match raises a review rather than rejecting
- `test_an_alias_match_says_it_matched_on_an_alias` — An alias match says it matched on an alias
- `test_a_strong_match_is_labelled_probable` — A strong match is labelled probable
- `test_the_screening_records_which_snapshot_it_used` — The screening records which snapshot it used
- `test_a_hit_is_audited_distinctly_from_a_clear_screen` — A hit is audited distinctly from a clear screen
- `test_clearing_a_hit_requires_a_note` — Clearing a hit requires a note
- `test_clearing_leaves_the_party_usable` — Clearing leaves the party usable
- `test_confirming_a_match_stops_the_party_being_used` — Confirming a match stops the party being used
- `test_a_screening_cannot_be_decided_twice` — A screening cannot be decided twice
- `test_the_queue_is_oldest_first` — The queue is oldest first
- `test_importing_replaces_the_previous_snapshot` — Importing replaces the previous snapshot
- `test_a_superseded_entry_is_kept_not_deleted` — A superseded entry is kept not deleted
- `test_importing_one_source_leaves_the_others_alone` — Importing one source leaves the others alone
- `test_an_unknown_source_is_refused` — An unknown source is refused
- `test_status_reports_the_oldest_list_not_the_newest` — Status reports the oldest list not the newest
- `test_a_fresh_list_is_not_stale` — A fresh list is not stale
- `test_status_says_when_nothing_is_loaded` — Status says when nothing is loaded
- `test_every_audited_action_reaches_the_siem` — Every audited action reaches the SIEM
- `test_a_siem_failure_never_breaks_the_audited_action` — A SIEM failure never breaks the audited action
- `test_teams_is_off_until_a_webhook_is_configured` — Teams is off until a webhook is configured
- `test_an_adaptive_card_puts_the_numbers_in_facts` — An adaptive card puts the numbers in facts
- `test_only_events_worth_interrupting_for_are_notifiable` — Only events worth interrupting for are notifiable
- `test_sharepoint_files_by_year_and_type` — Sharepoint files by year and type
- `test_an_ics_invite_is_well_formed` — An ics invite is well formed
- `test_ics_lines_are_folded_to_the_spec_limit` — Ics lines are folded to the spec limit
- `test_ics_escapes_a_comma` — Ics escapes a comma
- `test_a_renewal_invite_has_a_stable_uid` — A renewal invite has a stable uid
- `test_no_end_date_means_no_renewal_invite` — No end date means no renewal invite
- `test_a_cancelled_invite_says_so` — A cancelled invite says so
- `test_soap_is_off_by_default` — Soap is off by default
- `test_a_request_without_credentials_gets_a_fault` — A request without credentials gets a fault
- `test_a_bad_api_key_gets_a_fault` — A bad API key gets a fault
- `test_malformed_xml_gets_a_fault_not_a_stack_trace` — Malformed xml gets a fault not a stack trace
- `test_an_unknown_operation_lists_what_is_supported` — An unknown operation lists what is supported
- `test_getting_a_contract_over_soap` — Getting a contract over soap
- `test_a_missing_contract_gets_a_fault` — A missing contract gets a fault
- `test_creating_a_contract_over_soap_still_starts_as_a_draft` — Creating a contract over soap still starts as a draft
- `test_creating_without_a_title_gets_a_fault` — Creating without a title gets a fault
- `test_a_bad_date_gets_a_fault_rather_than_being_guessed` — A bad date gets a fault rather than being guessed
- `test_listing_is_capped` — Listing is capped
- `test_another_tenants_agreement_is_not_reachable_over_soap` — Another tenants agreement is not reachable over soap
- `test_the_wsdl_describes_the_operations_it_actually_has` — The wsdl describes the operations it actually has

</details>


#### SEC-14

**UAT-SEC-14-01** · Run the data protection suite

*Why it matters:* Masking, watermarking, antivirus and anti-automation.

*Automated by:* `test_data_protection.py` — 28 tests

<details><summary>Tests in this script</summary>

- `test_a_cnic_keeps_only_its_last_four` — A CNIC keeps only its last four
- `test_an_email_keeps_its_domain` — An email keeps its domain
- `test_a_phone_keeps_its_last_four` — A phone keeps its last four
- `test_money_is_masked_entirely` — Money is masked entirely
- `test_a_short_value_reveals_nothing` — A short value reveals nothing
- `test_an_empty_value_stays_empty` — An empty value stays empty
- `test_identifiers_are_masked_inside_free_text` — Identifiers are masked inside free text
- `test_ordinary_numbers_survive_masking` — Ordinary numbers survive masking
- `test_roles_that_may_see_a_field_see_it` — Roles that may see a field see it
- `test_masking_is_applied_to_the_response_payload` — Masking is applied to the response payload
- `test_a_permitted_role_gets_the_real_values` — A permitted role gets the real values
- `test_masking_does_not_mutate_the_original` — Masking does not mutate the original
- `test_the_watermark_names_the_viewer_and_the_moment` — The watermark names the viewer and the moment
- `test_stamping_produces_a_readable_pdf` — Stamping produces a readable PDF
- `test_a_document_that_cannot_be_watermarked_is_still_served` — A document that cannot be watermarked is still served
- `test_view_only_headers_do_not_offer_a_download` — View only headers do not offer a download
- `test_download_headers_attach_when_allowed` — Download headers attach when allowed
- `test_the_eicar_test_file_is_always_rejected` — The eicar test file is always rejected
- `test_scan_or_raise_refuses_an_infected_upload` — Scan or raise refuses an infected upload
- `test_an_unconfigured_scanner_says_so_rather_than_claiming_clean` — An unconfigured scanner says so rather than claiming clean
- `test_the_scanner_fails_closed_when_it_cannot_be_reached` — The scanner fails closed when it cannot be reached
- `test_the_status_states_plainly_whether_uploads_are_protected` — The status states plainly whether uploads are protected
- `test_a_challenge_is_only_demanded_after_repeated_failures` — A challenge is only demanded after repeated failures
- `test_a_successful_sign_in_clears_the_backoff` — A successful sign in clears the backoff
- `test_a_correct_proof_of_work_verifies` — A correct proof of work verifies
- `test_a_wrong_nonce_does_not_verify` — A wrong nonce does not verify
- `test_an_empty_proof_does_not_verify` — An empty proof does not verify
- `test_the_challenge_explains_itself` — The challenge explains itself

</details>


#### SEC-15

**UAT-SEC-15-01** · Run the data protection suite

*Why it matters:* Masking, watermarking, antivirus and anti-automation.

*Automated by:* `test_data_protection.py` — 28 tests

<details><summary>Tests in this script</summary>

- `test_a_cnic_keeps_only_its_last_four` — A CNIC keeps only its last four
- `test_an_email_keeps_its_domain` — An email keeps its domain
- `test_a_phone_keeps_its_last_four` — A phone keeps its last four
- `test_money_is_masked_entirely` — Money is masked entirely
- `test_a_short_value_reveals_nothing` — A short value reveals nothing
- `test_an_empty_value_stays_empty` — An empty value stays empty
- `test_identifiers_are_masked_inside_free_text` — Identifiers are masked inside free text
- `test_ordinary_numbers_survive_masking` — Ordinary numbers survive masking
- `test_roles_that_may_see_a_field_see_it` — Roles that may see a field see it
- `test_masking_is_applied_to_the_response_payload` — Masking is applied to the response payload
- `test_a_permitted_role_gets_the_real_values` — A permitted role gets the real values
- `test_masking_does_not_mutate_the_original` — Masking does not mutate the original
- `test_the_watermark_names_the_viewer_and_the_moment` — The watermark names the viewer and the moment
- `test_stamping_produces_a_readable_pdf` — Stamping produces a readable PDF
- `test_a_document_that_cannot_be_watermarked_is_still_served` — A document that cannot be watermarked is still served
- `test_view_only_headers_do_not_offer_a_download` — View only headers do not offer a download
- `test_download_headers_attach_when_allowed` — Download headers attach when allowed
- `test_the_eicar_test_file_is_always_rejected` — The eicar test file is always rejected
- `test_scan_or_raise_refuses_an_infected_upload` — Scan or raise refuses an infected upload
- `test_an_unconfigured_scanner_says_so_rather_than_claiming_clean` — An unconfigured scanner says so rather than claiming clean
- `test_the_scanner_fails_closed_when_it_cannot_be_reached` — The scanner fails closed when it cannot be reached
- `test_the_status_states_plainly_whether_uploads_are_protected` — The status states plainly whether uploads are protected
- `test_a_challenge_is_only_demanded_after_repeated_failures` — A challenge is only demanded after repeated failures
- `test_a_successful_sign_in_clears_the_backoff` — A successful sign in clears the backoff
- `test_a_correct_proof_of_work_verifies` — A correct proof of work verifies
- `test_a_wrong_nonce_does_not_verify` — A wrong nonce does not verify
- `test_an_empty_proof_does_not_verify` — An empty proof does not verify
- `test_the_challenge_explains_itself` — The challenge explains itself

</details>


#### SEC-16

**UAT-SEC-16-01** · Run the data protection suite

*Why it matters:* Masking, watermarking, antivirus and anti-automation.

*Automated by:* `test_data_protection.py` — 28 tests

<details><summary>Tests in this script</summary>

- `test_a_cnic_keeps_only_its_last_four` — A CNIC keeps only its last four
- `test_an_email_keeps_its_domain` — An email keeps its domain
- `test_a_phone_keeps_its_last_four` — A phone keeps its last four
- `test_money_is_masked_entirely` — Money is masked entirely
- `test_a_short_value_reveals_nothing` — A short value reveals nothing
- `test_an_empty_value_stays_empty` — An empty value stays empty
- `test_identifiers_are_masked_inside_free_text` — Identifiers are masked inside free text
- `test_ordinary_numbers_survive_masking` — Ordinary numbers survive masking
- `test_roles_that_may_see_a_field_see_it` — Roles that may see a field see it
- `test_masking_is_applied_to_the_response_payload` — Masking is applied to the response payload
- `test_a_permitted_role_gets_the_real_values` — A permitted role gets the real values
- `test_masking_does_not_mutate_the_original` — Masking does not mutate the original
- `test_the_watermark_names_the_viewer_and_the_moment` — The watermark names the viewer and the moment
- `test_stamping_produces_a_readable_pdf` — Stamping produces a readable PDF
- `test_a_document_that_cannot_be_watermarked_is_still_served` — A document that cannot be watermarked is still served
- `test_view_only_headers_do_not_offer_a_download` — View only headers do not offer a download
- `test_download_headers_attach_when_allowed` — Download headers attach when allowed
- `test_the_eicar_test_file_is_always_rejected` — The eicar test file is always rejected
- `test_scan_or_raise_refuses_an_infected_upload` — Scan or raise refuses an infected upload
- `test_an_unconfigured_scanner_says_so_rather_than_claiming_clean` — An unconfigured scanner says so rather than claiming clean
- `test_the_scanner_fails_closed_when_it_cannot_be_reached` — The scanner fails closed when it cannot be reached
- `test_the_status_states_plainly_whether_uploads_are_protected` — The status states plainly whether uploads are protected
- `test_a_challenge_is_only_demanded_after_repeated_failures` — A challenge is only demanded after repeated failures
- `test_a_successful_sign_in_clears_the_backoff` — A successful sign in clears the backoff
- `test_a_correct_proof_of_work_verifies` — A correct proof of work verifies
- `test_a_wrong_nonce_does_not_verify` — A wrong nonce does not verify
- `test_an_empty_proof_does_not_verify` — An empty proof does not verify
- `test_the_challenge_explains_itself` — The challenge explains itself

</details>


#### SEC-17

**UAT-SEC-17-01** · Run the data protection suite

*Why it matters:* Masking, watermarking, antivirus and anti-automation.

*Automated by:* `test_data_protection.py` — 28 tests

<details><summary>Tests in this script</summary>

- `test_a_cnic_keeps_only_its_last_four` — A CNIC keeps only its last four
- `test_an_email_keeps_its_domain` — An email keeps its domain
- `test_a_phone_keeps_its_last_four` — A phone keeps its last four
- `test_money_is_masked_entirely` — Money is masked entirely
- `test_a_short_value_reveals_nothing` — A short value reveals nothing
- `test_an_empty_value_stays_empty` — An empty value stays empty
- `test_identifiers_are_masked_inside_free_text` — Identifiers are masked inside free text
- `test_ordinary_numbers_survive_masking` — Ordinary numbers survive masking
- `test_roles_that_may_see_a_field_see_it` — Roles that may see a field see it
- `test_masking_is_applied_to_the_response_payload` — Masking is applied to the response payload
- `test_a_permitted_role_gets_the_real_values` — A permitted role gets the real values
- `test_masking_does_not_mutate_the_original` — Masking does not mutate the original
- `test_the_watermark_names_the_viewer_and_the_moment` — The watermark names the viewer and the moment
- `test_stamping_produces_a_readable_pdf` — Stamping produces a readable PDF
- `test_a_document_that_cannot_be_watermarked_is_still_served` — A document that cannot be watermarked is still served
- `test_view_only_headers_do_not_offer_a_download` — View only headers do not offer a download
- `test_download_headers_attach_when_allowed` — Download headers attach when allowed
- `test_the_eicar_test_file_is_always_rejected` — The eicar test file is always rejected
- `test_scan_or_raise_refuses_an_infected_upload` — Scan or raise refuses an infected upload
- `test_an_unconfigured_scanner_says_so_rather_than_claiming_clean` — An unconfigured scanner says so rather than claiming clean
- `test_the_scanner_fails_closed_when_it_cannot_be_reached` — The scanner fails closed when it cannot be reached
- `test_the_status_states_plainly_whether_uploads_are_protected` — The status states plainly whether uploads are protected
- `test_a_challenge_is_only_demanded_after_repeated_failures` — A challenge is only demanded after repeated failures
- `test_a_successful_sign_in_clears_the_backoff` — A successful sign in clears the backoff
- `test_a_correct_proof_of_work_verifies` — A correct proof of work verifies
- `test_a_wrong_nonce_does_not_verify` — A wrong nonce does not verify
- `test_an_empty_proof_does_not_verify` — An empty proof does not verify
- `test_the_challenge_explains_itself` — The challenge explains itself

</details>


#### SEC-18

**UAT-SEC-18-01** · Run the password policy suite

*Why it matters:* Password strength policy — rejects weak, accepts strong, blocks user-data echoes.

*Automated by:* `test_password_policy.py` — 9 tests

<details><summary>Tests in this script</summary>

- `test_rejects_too_short` — Rejects too short
- `test_rejects_too_few_classes` — Rejects too few classes
- `test_rejects_common_password` — Rejects common password
- `test_rejects_sequential` — Rejects sequential
- `test_rejects_when_contains_email_localpart` — Rejects when contains email localpart
- `test_rejects_when_contains_name` — Rejects when contains name
- `test_accepts_strong_password` — Accepts strong password
- `test_only_dev_gets_the_shorter_minimum` — Only dev gets the shorter minimum
- `test_the_minimum_is_enforced_at_the_boundary` — The minimum is enforced at the boundary

</details>


#### SEC-22

**UAT-SEC-22-01** · Run the residency and profile suite

*Why it matters:* Data residency enforcement + the single-tenant deployment profile (Phase 0).

*Automated by:* `test_residency_and_profile.py` — 13 tests

<details><summary>Tests in this script</summary>

- `test_host_extraction` — Host extraction
- `test_private_endpoints_pass` — Private endpoints pass
- `test_public_endpoint_blocks_boot` — Public endpoint blocks boot
- `test_allowlist_permits_a_reviewed_exception` — Allowlist permits a reviewed exception
- `test_allowlist_accepts_cidr` — Allowlist accepts cidr
- `test_enforcement_can_be_reported_without_blocking` — Enforcement can be reported without blocking
- `test_anthropic_ocr_counts_as_egress` — Anthropic ocr counts as egress
- `test_unresolvable_host_is_not_a_violation` — Unresolvable host is not a violation
- `test_registration_disabled_in_single_tenant` — Registration disabled in single tenant
- `test_register_endpoint_is_gated` — Register endpoint is gated
- `test_sso_config_advertises_the_profile` — Sso config advertises the profile
- `test_saas_profile_cannot_disable_db_isolation` — Saas profile cannot disable db isolation
- `test_single_tenant_rejects_saas_shaped_config` — Single tenant rejects saas shaped config

</details>



### PKI and eSignature

#### PKI-01

**UAT-PKI-01-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>


#### PKI-02

**UAT-PKI-02-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>


#### PKI-03

**UAT-PKI-03-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>


#### PKI-04

**UAT-PKI-04-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>


#### PKI-05

**UAT-PKI-05-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>


#### PKI-06

**UAT-PKI-06-01** · Run the pki hsm suite

*Why it matters:* PKCS#11 keystore, exercised against a real token.

*Automated by:* `test_pki_hsm.py` — 7 tests

<details><summary>Tests in this script</summary>

- `test_key_is_generated_inside_the_token` — Key is generated inside the token
- `test_private_key_cannot_be_extracted` — Private key cannot be extracted
- `test_signature_verifies_against_the_token_public_key` — Signature verifies against the token public key
- `test_signer_proxy_drives_a_real_certificate_build` — Signer proxy drives a real certificate build
- `test_rsa_keys_work_too` — Rsa keys work too
- `test_destroy_removes_the_key_from_the_token` — Destroy removes the key from the token
- `test_full_hierarchy_provisions_on_the_token` — Full hierarchy provisions on the token

</details>


#### PKI-07

**UAT-PKI-07-01** · Run the pki hsm suite

*Why it matters:* PKCS#11 keystore, exercised against a real token.

*Automated by:* `test_pki_hsm.py` — 7 tests

<details><summary>Tests in this script</summary>

- `test_key_is_generated_inside_the_token` — Key is generated inside the token
- `test_private_key_cannot_be_extracted` — Private key cannot be extracted
- `test_signature_verifies_against_the_token_public_key` — Signature verifies against the token public key
- `test_signer_proxy_drives_a_real_certificate_build` — Signer proxy drives a real certificate build
- `test_rsa_keys_work_too` — Rsa keys work too
- `test_destroy_removes_the_key_from_the_token` — Destroy removes the key from the token
- `test_full_hierarchy_provisions_on_the_token` — Full hierarchy provisions on the token

</details>


#### PKI-08

**UAT-PKI-08-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>


#### PKI-09

**UAT-PKI-09-01** · Run the pki suite

*Why it matters:* PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

*Automated by:* `test_pki.py` — 52 tests

<details><summary>Tests in this script</summary>

- `test_root_is_self_signed_and_issuing_chains_to_it` — Root is self signed and issuing chains to it
- `test_issuing_ca_cannot_mint_further_cas` — Issuing ca cannot mint further cas
- `test_ocsp_responder_certificate_is_delegated_and_marked` — OCSP responder certificate is delegated and marked
- `test_provisioning_is_idempotent` — Provisioning is idempotent
- `test_serial_numbers_are_unpredictable` — Serial numbers are unpredictable
- `test_private_key_is_never_returned_by_the_interface` — Private key is never returned by the interface
- `test_key_material_is_encrypted_at_rest` — Key material is encrypted at rest
- `test_sign_round_trips_against_the_public_key` — Sign round trips against the public key
- `test_destroy_removes_the_key` — Destroy removes the key
- `test_certificate_cannot_be_issued_without_an_approved_request` — Certificate cannot be issued without an approved request
- `test_rejected_request_cannot_be_issued` — Rejected request cannot be issued
- `test_officer_cannot_approve_their_own_request` — Officer cannot approve their own request
- `test_non_admin_cannot_act_as_ra_officer` — Non admin cannot act as ra officer
- `test_duplicate_open_request_is_refused` — Duplicate open request is refused
- `test_dual_control_requires_two_distinct_officers` — Dual control requires two distinct officers
- `test_identity_evidence_is_carried_into_the_certificate_audit_entry` — Identity evidence is carried into the certificate audit entry
- `test_issued_certificate_chains_to_the_issuing_ca` — Issued certificate chains to the issuing ca
- `test_certificate_is_bound_to_the_signatory` — Certificate is bound to the signatory
- `test_certificate_carries_non_repudiation` — Certificate carries non repudiation
- `test_certificate_advertises_crl_and_ocsp` — Certificate advertises CRL and OCSP
- `test_shared_certificate_issuance_is_rejected` — Shared certificate issuance is rejected
- `test_leaf_never_outlives_its_issuer` — Leaf never outlives its issuer
- `test_renewal_preserves_binding_and_changes_the_serial` — Renewal preserves binding and changes the serial
- `test_suspension_blocks_signing_and_resumption_restores_it` — Suspension blocks signing and resumption restores it
- `test_revocation_is_terminal` — Revocation is terminal
- `test_unknown_revocation_reason_is_rejected` — Unknown revocation reason is rejected
- `test_expired_certificate_cannot_sign` — Expired certificate cannot sign
- `test_expire_sweep_frees_the_subject_slot` — Expire sweep frees the subject slot
- `test_revoked_serial_appears_in_a_signed_crl` — Revoked serial appears in a signed CRL
- `test_active_certificate_is_absent_from_the_crl` — Active certificate is absent from the CRL
- `test_crl_number_is_monotonic` — CRL number is monotonic
- `test_suspended_certificate_is_listed_as_certificate_hold` — Suspended certificate is listed as certificate hold
- `test_delta_crl_requires_a_base` — Delta CRL requires a base
- `test_delta_crl_is_marked_as_a_delta` — Delta CRL is marked as a delta
- `test_active_certificate_is_good` — Active certificate is good
- `test_revoked_certificate_is_revoked_with_the_reason` — Revoked certificate is revoked with the reason
- `test_suspended_certificate_is_revoked_on_hold` — Suspended certificate is revoked on hold
- `test_nonce_is_echoed` — Nonce is echoed
- `test_response_is_signed_by_the_delegated_responder` — Response is signed by the delegated responder
- `test_unissued_serial_is_unknown_not_good` — Unissued serial is unknown not good
- `test_malformed_request_does_not_raise` — Malformed request does not raise
- `test_responder_identifies_the_issuer_without_a_tenant_hint` — Responder identifies the issuer without a tenant hint
- `test_unrelated_issuer_gets_unauthorized` — Unrelated issuer gets unauthorized
- `test_rejects_everything_when_no_trust_anchors_are_configured` — Rejects everything when no trust anchors are configured
- `test_accepts_a_valid_third_party_chain` — Accepts a valid third party chain
- `test_rejects_an_expired_certificate` — Rejects an expired certificate
- `test_rejects_a_certificate_from_an_untrusted_root` — Rejects a certificate from an untrusted root
- `test_our_own_certificates_validate_against_our_own_root` — Our own certificates validate against our own root
- `test_adding_the_same_anchor_twice_does_not_duplicate` — Adding the same anchor twice does not duplicate
- `test_cross_certification_preserves_existing_certificates` — Cross certification preserves existing certificates
- `test_trust_anchors_live_in_the_database_not_a_file` — Trust anchors live in the database not a file
- `test_certificates_do_not_leak_between_tenants` — Certificates do not leak between tenants

</details>



### Integrations

#### INT-04

**UAT-INT-04-01** · Run the saml suite

*Why it matters:* SAML 2.0 service provider.

*Automated by:* `test_saml.py` — 30 tests

<details><summary>Tests in this script</summary>

- `test_saml_is_off_until_configured` — Saml is off until configured
- `test_enabling_without_a_certificate_is_still_off` — Enabling without a certificate is still off
- `test_metadata_names_the_real_endpoints` — Metadata names the real endpoints
- `test_a_bare_base64_certificate_is_accepted` — A bare base64 certificate is accepted
- `test_the_authn_request_is_deflated_and_encoded` — The authn request is deflated and encoded
- `test_relay_state_is_carried_through` — Relay state is carried through
- `test_a_properly_signed_assertion_is_accepted` — A properly signed assertion is accepted
- `test_an_unsigned_assertion_is_rejected` — An unsigned assertion is rejected
- `test_an_assertion_signed_by_another_idp_is_rejected` — An assertion signed by another idp is rejected
- `test_a_tampered_assertion_is_rejected` — A tampered assertion is rejected
- `test_an_assertion_for_another_service_is_rejected` — An assertion for another service is rejected
- `test_an_expired_assertion_is_rejected` — An expired assertion is rejected
- `test_an_assertion_from_the_future_is_rejected` — An assertion from the future is rejected
- `test_small_clock_skew_is_tolerated` — Small clock skew is tolerated
- `test_an_assertion_cannot_be_replayed` — An assertion cannot be replayed
- `test_a_response_answering_a_different_request_is_rejected` — A response answering a different request is rejected
- `test_a_response_matching_our_request_is_accepted` — A response matching our request is accepted
- `test_an_assertion_addressed_elsewhere_is_rejected` — An assertion addressed elsewhere is rejected
- `test_an_idp_initiated_assertion_is_accepted` — An idp initiated assertion is accepted
- `test_an_assertion_without_an_email_is_rejected` — An assertion without an email is rejected
- `test_rubbish_is_rejected_without_exploding` — Rubbish is rejected without exploding
- `test_a_mapped_group_selects_the_role` — A mapped group selects the role
- `test_an_unmapped_group_falls_back_to_the_default_role` — An unmapped group falls back to the default role
- `test_no_groups_at_all_still_gets_the_default_role` — No groups at all still gets the default role
- `test_logout_redirects_to_the_idp_when_it_has_an_slo_endpoint` — Logout redirects to the idp when it has an slo endpoint
- `test_logout_falls_back_locally_when_the_idp_has_no_slo` — Logout falls back locally when the idp has no slo
- `test_the_endpoints_are_absent_until_saml_is_configured` — The endpoints are absent until saml is configured
- `test_metadata_is_served_as_xml` — Metadata is served as xml
- `test_login_redirects_to_the_idp` — Login redirects to the idp
- `test_a_rejected_assertion_does_not_explain_itself_to_the_browser` — A rejected assertion does not explain itself to the browser

</details>


#### INT-06

**UAT-INT-06-01** · Run the integrations suite

*Why it matters:* SIEM feed and sanctions screening.

*Automated by:* `test_integrations.py` — 65 tests

<details><summary>Tests in this script</summary>

- `test_actions_land_in_the_right_siem_category` — Actions land in the right SIEM category
- `test_a_failed_login_outranks_a_successful_one` — A failed login outranks a successful one
- `test_a_broken_audit_chain_is_critical` — A broken audit chain is critical
- `test_an_unknown_action_is_still_reported` — An unknown action is still reported
- `test_cef_has_the_required_header_fields` — CEF has the required header fields
- `test_cef_severity_runs_the_opposite_way_to_syslog` — CEF severity runs the opposite way to syslog
- `test_cef_carries_the_actor_ip_and_chain_position` — CEF carries the actor ip and chain position
- `test_cef_escapes_a_pipe_in_the_header` — CEF escapes a pipe in the header
- `test_cef_escapes_an_equals_sign_in_the_extension` — CEF escapes an equals sign in the extension
- `test_clf_is_a_parseable_web_log_line` — Clf is a parseable web log line
- `test_the_syslog_frame_is_octet_counted` — The syslog frame is octet counted
- `test_the_syslog_priority_encodes_the_severity` — The syslog priority encodes the severity
- `test_the_feed_is_off_until_configured` — The feed is off until configured
- `test_emitting_while_disabled_is_a_no_op` — Emitting while disabled is a no op
- `test_events_reach_a_listening_collector` — Events reach a listening collector
- `test_an_unreachable_collector_does_not_raise` — An unreachable collector does not raise
- `test_a_batch_reports_what_got_through` — A batch reports what got through
- `test_transliterations_and_reorderings_still_match` — Transliterations and reorderings still match
- `test_different_people_do_not_match` — Different people do not match
- `test_a_single_shared_common_name_is_not_a_match` — A single shared common name is not a match
- `test_a_shorter_name_inside_a_longer_one_matches` — A shorter name inside a longer one matches
- `test_normalisation_drops_entity_noise` — Normalisation drops entity noise
- `test_a_clean_screen_is_still_recorded` — A clean screen is still recorded
- `test_a_match_raises_a_review_rather_than_rejecting` — A match raises a review rather than rejecting
- `test_an_alias_match_says_it_matched_on_an_alias` — An alias match says it matched on an alias
- `test_a_strong_match_is_labelled_probable` — A strong match is labelled probable
- `test_the_screening_records_which_snapshot_it_used` — The screening records which snapshot it used
- `test_a_hit_is_audited_distinctly_from_a_clear_screen` — A hit is audited distinctly from a clear screen
- `test_clearing_a_hit_requires_a_note` — Clearing a hit requires a note
- `test_clearing_leaves_the_party_usable` — Clearing leaves the party usable
- `test_confirming_a_match_stops_the_party_being_used` — Confirming a match stops the party being used
- `test_a_screening_cannot_be_decided_twice` — A screening cannot be decided twice
- `test_the_queue_is_oldest_first` — The queue is oldest first
- `test_importing_replaces_the_previous_snapshot` — Importing replaces the previous snapshot
- `test_a_superseded_entry_is_kept_not_deleted` — A superseded entry is kept not deleted
- `test_importing_one_source_leaves_the_others_alone` — Importing one source leaves the others alone
- `test_an_unknown_source_is_refused` — An unknown source is refused
- `test_status_reports_the_oldest_list_not_the_newest` — Status reports the oldest list not the newest
- `test_a_fresh_list_is_not_stale` — A fresh list is not stale
- `test_status_says_when_nothing_is_loaded` — Status says when nothing is loaded
- `test_every_audited_action_reaches_the_siem` — Every audited action reaches the SIEM
- `test_a_siem_failure_never_breaks_the_audited_action` — A SIEM failure never breaks the audited action
- `test_teams_is_off_until_a_webhook_is_configured` — Teams is off until a webhook is configured
- `test_an_adaptive_card_puts_the_numbers_in_facts` — An adaptive card puts the numbers in facts
- `test_only_events_worth_interrupting_for_are_notifiable` — Only events worth interrupting for are notifiable
- `test_sharepoint_files_by_year_and_type` — Sharepoint files by year and type
- `test_an_ics_invite_is_well_formed` — An ics invite is well formed
- `test_ics_lines_are_folded_to_the_spec_limit` — Ics lines are folded to the spec limit
- `test_ics_escapes_a_comma` — Ics escapes a comma
- `test_a_renewal_invite_has_a_stable_uid` — A renewal invite has a stable uid
- `test_no_end_date_means_no_renewal_invite` — No end date means no renewal invite
- `test_a_cancelled_invite_says_so` — A cancelled invite says so
- `test_soap_is_off_by_default` — Soap is off by default
- `test_a_request_without_credentials_gets_a_fault` — A request without credentials gets a fault
- `test_a_bad_api_key_gets_a_fault` — A bad API key gets a fault
- `test_malformed_xml_gets_a_fault_not_a_stack_trace` — Malformed xml gets a fault not a stack trace
- `test_an_unknown_operation_lists_what_is_supported` — An unknown operation lists what is supported
- `test_getting_a_contract_over_soap` — Getting a contract over soap
- `test_a_missing_contract_gets_a_fault` — A missing contract gets a fault
- `test_creating_a_contract_over_soap_still_starts_as_a_draft` — Creating a contract over soap still starts as a draft
- `test_creating_without_a_title_gets_a_fault` — Creating without a title gets a fault
- `test_a_bad_date_gets_a_fault_rather_than_being_guessed` — A bad date gets a fault rather than being guessed
- `test_listing_is_capped` — Listing is capped
- `test_another_tenants_agreement_is_not_reachable_over_soap` — Another tenants agreement is not reachable over soap
- `test_the_wsdl_describes_the_operations_it_actually_has` — The wsdl describes the operations it actually has

</details>


#### INT-07

**UAT-INT-07-01** · Run the infrastructure adapters suite

*Why it matters:* Storage, secrets, email and SMS (Phase 10 — coverage on the infrastructure adapters).

*Automated by:* `test_infrastructure_adapters.py` — 34 tests

<details><summary>Tests in this script</summary>

- `test_a_tenant_key_is_prefixed_with_its_tenant` — A tenant key is prefixed with its tenant
- `test_key_parts_cannot_escape_the_prefix_with_a_leading_slash` — Key parts cannot escape the prefix with a leading slash
- `test_windows_separators_are_normalised` — Windows separators are normalised
- `test_empty_parts_are_dropped` — Empty parts are dropped
- `test_a_local_object_round_trips` — A local object round trips
- `test_a_missing_object_does_not_exist` — A missing object does not exist
- `test_deleting_something_that_is_not_there_is_not_an_error` — Deleting something that is not there is not an error
- `test_a_traversing_key_is_refused` — A traversing key is refused
- `test_move_relocates_and_removes_the_original` — Move relocates and removes the original
- `test_moving_onto_itself_is_a_no_op_not_a_deletion` — Moving onto itself is a no op not a deletion
- `test_nested_directories_are_created_on_write` — Nested directories are created on write
- `test_get_storage_returns_the_local_backend_when_s3_is_off` — Get storage returns the local backend when s3 is off
- `test_a_configured_box_encrypts_and_round_trips` — A configured box encrypts and round trips
- `test_an_unconfigured_box_tags_plaintext_rather_than_pretending` — An unconfigured box tags plaintext rather than pretending
- `test_none_stays_none_in_both_directions` — None stays none in both directions
- `test_a_key_chain_decrypts_what_an_older_key_encrypted` — A key chain decrypts what an older key encrypted
- `test_rotate_re_encrypts_under_the_current_key` — Rotate re encrypts under the current key
- `test_decrypting_without_the_right_key_fails_loudly` — Decrypting without the right key fails loudly
- `test_ciphertext_found_with_no_keys_configured_is_an_error` — Ciphertext found with no keys configured is an error
- `test_an_unprefixed_legacy_value_is_read_as_plaintext` — An unprefixed legacy value is read as plaintext
- `test_a_raw_32_byte_key_is_accepted` — A raw 32 byte key is accepted
- `test_a_nonsense_key_is_rejected_at_startup_not_at_use` — A nonsense key is rejected at startup not at use
- `test_every_spelling_of_a_number_normalises_to_one_value` — Every spelling of a number normalises to one value
- `test_an_empty_number_normalises_to_empty_not_a_country_code` — An empty number normalises to empty not a country code
- `test_masking_shows_enough_to_reconcile_and_no_more` — Masking shows enough to reconcile and no more
- `test_email_masking` — Email masking
- `test_a_failed_sms_is_recorded_as_failed` — A failed sms is recorded as failed
- `test_a_successful_sms_is_recorded_with_its_provider_reference` — A successful sms is recorded with its provider reference
- `test_sms_lands_in_the_same_outbox_as_email` — Sms lands in the same outbox as email
- `test_an_email_is_queued_and_marked_sent` — An email is queued and marked sent
- `test_a_delivery_failure_is_recorded_rather_than_raised` — A delivery failure is recorded rather than raised
- `test_the_flusher_retries_a_failed_row` — The flusher retries a failed row
- `test_the_flusher_gives_up_after_the_attempt_cap` — The flusher gives up after the attempt cap
- `test_the_flusher_never_hands_a_phone_number_to_smtp` — The flusher never hands a phone number to smtp

</details>


#### INT-08

**UAT-INT-08-01** · Run the infrastructure adapters suite

*Why it matters:* Storage, secrets, email and SMS (Phase 10 — coverage on the infrastructure adapters).

*Automated by:* `test_infrastructure_adapters.py` — 34 tests

<details><summary>Tests in this script</summary>

- `test_a_tenant_key_is_prefixed_with_its_tenant` — A tenant key is prefixed with its tenant
- `test_key_parts_cannot_escape_the_prefix_with_a_leading_slash` — Key parts cannot escape the prefix with a leading slash
- `test_windows_separators_are_normalised` — Windows separators are normalised
- `test_empty_parts_are_dropped` — Empty parts are dropped
- `test_a_local_object_round_trips` — A local object round trips
- `test_a_missing_object_does_not_exist` — A missing object does not exist
- `test_deleting_something_that_is_not_there_is_not_an_error` — Deleting something that is not there is not an error
- `test_a_traversing_key_is_refused` — A traversing key is refused
- `test_move_relocates_and_removes_the_original` — Move relocates and removes the original
- `test_moving_onto_itself_is_a_no_op_not_a_deletion` — Moving onto itself is a no op not a deletion
- `test_nested_directories_are_created_on_write` — Nested directories are created on write
- `test_get_storage_returns_the_local_backend_when_s3_is_off` — Get storage returns the local backend when s3 is off
- `test_a_configured_box_encrypts_and_round_trips` — A configured box encrypts and round trips
- `test_an_unconfigured_box_tags_plaintext_rather_than_pretending` — An unconfigured box tags plaintext rather than pretending
- `test_none_stays_none_in_both_directions` — None stays none in both directions
- `test_a_key_chain_decrypts_what_an_older_key_encrypted` — A key chain decrypts what an older key encrypted
- `test_rotate_re_encrypts_under_the_current_key` — Rotate re encrypts under the current key
- `test_decrypting_without_the_right_key_fails_loudly` — Decrypting without the right key fails loudly
- `test_ciphertext_found_with_no_keys_configured_is_an_error` — Ciphertext found with no keys configured is an error
- `test_an_unprefixed_legacy_value_is_read_as_plaintext` — An unprefixed legacy value is read as plaintext
- `test_a_raw_32_byte_key_is_accepted` — A raw 32 byte key is accepted
- `test_a_nonsense_key_is_rejected_at_startup_not_at_use` — A nonsense key is rejected at startup not at use
- `test_every_spelling_of_a_number_normalises_to_one_value` — Every spelling of a number normalises to one value
- `test_an_empty_number_normalises_to_empty_not_a_country_code` — An empty number normalises to empty not a country code
- `test_masking_shows_enough_to_reconcile_and_no_more` — Masking shows enough to reconcile and no more
- `test_email_masking` — Email masking
- `test_a_failed_sms_is_recorded_as_failed` — A failed sms is recorded as failed
- `test_a_successful_sms_is_recorded_with_its_provider_reference` — A successful sms is recorded with its provider reference
- `test_sms_lands_in_the_same_outbox_as_email` — Sms lands in the same outbox as email
- `test_an_email_is_queued_and_marked_sent` — An email is queued and marked sent
- `test_a_delivery_failure_is_recorded_rather_than_raised` — A delivery failure is recorded rather than raised
- `test_the_flusher_retries_a_failed_row` — The flusher retries a failed row
- `test_the_flusher_gives_up_after_the_attempt_cap` — The flusher gives up after the attempt cap
- `test_the_flusher_never_hands_a_phone_number_to_smtp` — The flusher never hands a phone number to smtp

</details>


#### INT-09

**UAT-INT-09-01** · Run the integrations suite

*Why it matters:* SIEM feed and sanctions screening.

*Automated by:* `test_integrations.py` — 65 tests

<details><summary>Tests in this script</summary>

- `test_actions_land_in_the_right_siem_category` — Actions land in the right SIEM category
- `test_a_failed_login_outranks_a_successful_one` — A failed login outranks a successful one
- `test_a_broken_audit_chain_is_critical` — A broken audit chain is critical
- `test_an_unknown_action_is_still_reported` — An unknown action is still reported
- `test_cef_has_the_required_header_fields` — CEF has the required header fields
- `test_cef_severity_runs_the_opposite_way_to_syslog` — CEF severity runs the opposite way to syslog
- `test_cef_carries_the_actor_ip_and_chain_position` — CEF carries the actor ip and chain position
- `test_cef_escapes_a_pipe_in_the_header` — CEF escapes a pipe in the header
- `test_cef_escapes_an_equals_sign_in_the_extension` — CEF escapes an equals sign in the extension
- `test_clf_is_a_parseable_web_log_line` — Clf is a parseable web log line
- `test_the_syslog_frame_is_octet_counted` — The syslog frame is octet counted
- `test_the_syslog_priority_encodes_the_severity` — The syslog priority encodes the severity
- `test_the_feed_is_off_until_configured` — The feed is off until configured
- `test_emitting_while_disabled_is_a_no_op` — Emitting while disabled is a no op
- `test_events_reach_a_listening_collector` — Events reach a listening collector
- `test_an_unreachable_collector_does_not_raise` — An unreachable collector does not raise
- `test_a_batch_reports_what_got_through` — A batch reports what got through
- `test_transliterations_and_reorderings_still_match` — Transliterations and reorderings still match
- `test_different_people_do_not_match` — Different people do not match
- `test_a_single_shared_common_name_is_not_a_match` — A single shared common name is not a match
- `test_a_shorter_name_inside_a_longer_one_matches` — A shorter name inside a longer one matches
- `test_normalisation_drops_entity_noise` — Normalisation drops entity noise
- `test_a_clean_screen_is_still_recorded` — A clean screen is still recorded
- `test_a_match_raises_a_review_rather_than_rejecting` — A match raises a review rather than rejecting
- `test_an_alias_match_says_it_matched_on_an_alias` — An alias match says it matched on an alias
- `test_a_strong_match_is_labelled_probable` — A strong match is labelled probable
- `test_the_screening_records_which_snapshot_it_used` — The screening records which snapshot it used
- `test_a_hit_is_audited_distinctly_from_a_clear_screen` — A hit is audited distinctly from a clear screen
- `test_clearing_a_hit_requires_a_note` — Clearing a hit requires a note
- `test_clearing_leaves_the_party_usable` — Clearing leaves the party usable
- `test_confirming_a_match_stops_the_party_being_used` — Confirming a match stops the party being used
- `test_a_screening_cannot_be_decided_twice` — A screening cannot be decided twice
- `test_the_queue_is_oldest_first` — The queue is oldest first
- `test_importing_replaces_the_previous_snapshot` — Importing replaces the previous snapshot
- `test_a_superseded_entry_is_kept_not_deleted` — A superseded entry is kept not deleted
- `test_importing_one_source_leaves_the_others_alone` — Importing one source leaves the others alone
- `test_an_unknown_source_is_refused` — An unknown source is refused
- `test_status_reports_the_oldest_list_not_the_newest` — Status reports the oldest list not the newest
- `test_a_fresh_list_is_not_stale` — A fresh list is not stale
- `test_status_says_when_nothing_is_loaded` — Status says when nothing is loaded
- `test_every_audited_action_reaches_the_siem` — Every audited action reaches the SIEM
- `test_a_siem_failure_never_breaks_the_audited_action` — A SIEM failure never breaks the audited action
- `test_teams_is_off_until_a_webhook_is_configured` — Teams is off until a webhook is configured
- `test_an_adaptive_card_puts_the_numbers_in_facts` — An adaptive card puts the numbers in facts
- `test_only_events_worth_interrupting_for_are_notifiable` — Only events worth interrupting for are notifiable
- `test_sharepoint_files_by_year_and_type` — Sharepoint files by year and type
- `test_an_ics_invite_is_well_formed` — An ics invite is well formed
- `test_ics_lines_are_folded_to_the_spec_limit` — Ics lines are folded to the spec limit
- `test_ics_escapes_a_comma` — Ics escapes a comma
- `test_a_renewal_invite_has_a_stable_uid` — A renewal invite has a stable uid
- `test_no_end_date_means_no_renewal_invite` — No end date means no renewal invite
- `test_a_cancelled_invite_says_so` — A cancelled invite says so
- `test_soap_is_off_by_default` — Soap is off by default
- `test_a_request_without_credentials_gets_a_fault` — A request without credentials gets a fault
- `test_a_bad_api_key_gets_a_fault` — A bad API key gets a fault
- `test_malformed_xml_gets_a_fault_not_a_stack_trace` — Malformed xml gets a fault not a stack trace
- `test_an_unknown_operation_lists_what_is_supported` — An unknown operation lists what is supported
- `test_getting_a_contract_over_soap` — Getting a contract over soap
- `test_a_missing_contract_gets_a_fault` — A missing contract gets a fault
- `test_creating_a_contract_over_soap_still_starts_as_a_draft` — Creating a contract over soap still starts as a draft
- `test_creating_without_a_title_gets_a_fault` — Creating without a title gets a fault
- `test_a_bad_date_gets_a_fault_rather_than_being_guessed` — A bad date gets a fault rather than being guessed
- `test_listing_is_capped` — Listing is capped
- `test_another_tenants_agreement_is_not_reachable_over_soap` — Another tenants agreement is not reachable over soap
- `test_the_wsdl_describes_the_operations_it_actually_has` — The wsdl describes the operations it actually has

</details>


#### INT-10

**UAT-INT-10-01** · Run the renewals and webhooks suite

*Why it matters:* The renewal sweep and webhook dispatch (Phase 10 — coverage on two beat-driven services).

*Automated by:* `test_renewals_and_webhooks.py` — 34 tests

<details><summary>Tests in this script</summary>

- `test_a_contract_inside_the_window_is_flagged_expiring` — A contract inside the window is flagged expiring
- `test_a_contract_beyond_the_window_is_left_alone` — A contract beyond the window is left alone
- `test_a_contract_past_its_end_date_expires` — A contract past its end date expires
- `test_a_contract_already_expiring_still_expires` — A contract already expiring still expires
- `test_a_contract_with_no_end_date_is_untouched` — A contract with no end date is untouched
- `test_a_draft_is_not_swept` — A draft is not swept
- `test_the_expired_notice_fires_once_not_on_every_beat` — The expired notice fires once not on every beat
- `test_the_follow_up_reminders_fire_at_their_thresholds` — The follow up reminders fire at their thresholds
- `test_the_same_threshold_does_not_re_fire` — The same threshold does not re fire
- `test_a_reminder_is_skipped_when_there_is_nobody_to_tell` — A reminder is skipped when there is nobody to tell
- `test_a_pending_obligation_past_its_date_becomes_overdue` — A pending obligation past its date becomes overdue
- `test_a_completed_obligation_is_not_reopened` — A completed obligation is not reopened
- `test_renewing_creates_a_draft_successor_and_closes_the_original` — Renewing creates a draft successor and closes the original
- `test_the_successor_starts_the_day_after_the_original_ends` — The successor starts the day after the original ends
- `test_the_successor_inherits_the_original_term_length` — The successor inherits the original term length
- `test_a_contract_with_no_dates_renews_for_twelve_months` — A contract with no dates renews for twelve months
- `test_explicit_dates_win_over_the_defaults` — Explicit dates win over the defaults
- `test_a_draft_cannot_be_renewed` — A draft cannot be renewed
- `test_the_successor_gets_its_own_reference_and_first_version` — The successor gets its own reference and first version
- `test_the_chain_links_both_ways` — The chain links both ways
- `test_a_leap_day_renewal_lands_on_a_real_date` — A leap day renewal lands on a real date
- `test_the_signature_binds_the_timestamp_to_the_body` — The signature binds the timestamp to the body
- `test_a_different_secret_produces_a_different_signature` — A different secret produces a different signature
- `test_the_signature_is_verifiable_by_a_receiver` — The signature is verifiable by a receiver
- `test_a_new_secret_is_long_enough_to_be_a_secret` — A new secret is long enough to be a secret
- `test_subscription_matching` — Subscription matching
- `test_a_successful_delivery_is_recorded` — A successful delivery is recorded
- `test_a_non_2xx_response_is_a_failure` — A non 2xx response is a failure
- `test_an_unreachable_endpoint_does_not_take_down_the_caller` — An unreachable endpoint does not take down the caller
- `test_an_inactive_endpoint_receives_nothing` — An inactive endpoint receives nothing
- `test_an_endpoint_that_did_not_subscribe_receives_nothing` — An endpoint that did not subscribe receives nothing
- `test_another_tenants_endpoint_is_never_called` — Another tenants endpoint is never called
- `test_the_delivery_carries_the_signature_and_event_headers` — The delivery carries the signature and event headers
- `test_dispatch_with_no_endpoints_is_a_cheap_no_op` — Dispatch with no endpoints is a cheap no op

</details>



### Acceptance Criteria

#### AC-07

**UAT-AC-07-01** · Run the audit chain suite

*Why it matters:* Audit-log tamper-evidence chain — verifies that every audit row is HMAC-linked, that verification detects deletions and in-place edits, and that pre-chain rows are ignored.

*Automated by:* `test_audit_chain.py` — 9 tests

<details><summary>Tests in this script</summary>

- `test_two_entries_in_one_transaction_chain_correctly` — Two entries in one transaction chain correctly
- `test_each_row_chains_to_the_previous` — Each row chains to the previous
- `test_verify_chain_is_ok_on_clean_data` — Verify chain is ok on clean data
- `test_verify_detects_in_place_edit` — Verify detects in place edit
- `test_verify_detects_row_deletion` — Verify detects row deletion
- `test_chain_is_per_tenant` — Chain is per tenant
- `test_rows_in_the_same_tick_still_chain_in_insertion_order` — Rows in the same tick still chain in insertion order
- `test_deleting_a_row_written_in_a_tied_tick_is_still_detected` — Deleting a row written in a tied tick is still detected
- `test_an_edit_in_a_tied_tick_is_still_detected` — An edit in a tied tick is still detected

</details>



---

## 3. Requirements with no cited test

None — every requirement in the Compliance Matrix cites at least one test.

---

## 4. Manual scripts

Written by hand because they need judgement a test cannot make. They are listed here so 
the book is complete; the scripts themselves are maintained alongside it.

| Requirement | Why a person has to accept it |
|---|---|
| BB-04 | Whether the flow is genuinely usable by somebody who is not digitally literate is a judgement a person from that population has to make. |
| BB-07 | Urdu terminology has to be read by MMBL's legal team; a passing test proves the strings render, not that they are correct. |
| BB-08 | Automated checks find roughly a third of accessibility problems. Reading order, alt-text accuracy and screen-reader completion need a human. |
| SEC-21 | Third-party penetration testing, by a vendor MMBL appoints. |
| SOW-13 | The approval matrix must match MMBL's actual delegation policy, which no test can know. |
| TEC-11 | Patch turnaround is observed over time, not asserted in a test run. |

