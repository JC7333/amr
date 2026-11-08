# The signed mandate PDF: `attach_signed_mandate_pdf`

Status: implemented (schema v10). Step 2 of the principal identity work: step 1 is
`prepare_mandate_pdf` (`docs/principal-signature-spec.md`, section 2 bis); step 3,
comparing the signer with the people entitled to act for the principal, is not done.

## 1. Purpose

An Ed25519 key registered with `register_principal_key` proves that the same key signed
every mandate in a principal's name; for an ordinary `principal_id` it does not prove
who holds the key (first registration wins). A principal that already has a signature
certificate (for example an eIDAS qualified certificate on a smart card or a remote
signing service) can sign the PDF of the mandate with the tool it uses for its
contracts. `attach_signed_mandate_pdf` checks that signature and records who the
certificate names, next to the mandate, in the registry's chained records.

## 2. Flow

1. `prepare_mandate_pdf(...)` returns the mandate PDF (`pdf_base64`).
2. The principal signs the PDF with its own tool, as a PAdES signature appended to the
   file (incremental update; this is how signing tools save a signed PDF). For a
   mandate signed with the principal's Ed25519 key, it also signs `payload` as before.
3. `create_mandate(...)` registers the mandate (unchanged).
4. `attach_signed_mandate_pdf(mandate_id, signed_pdf_base64)` checks the signed file and
   records it. This can happen at any time after step 3; the 900-second window of
   `signed_at` concerns `create_mandate` only.
5. `get_proof(mandate_id)` shows the records (`pdf_signatures`) and
   `chain_integrity.pdf_signatures_intact`.

## 3. What is checked, offline

The check uses pyHanko and makes no network call (no OCSP, no CRL, no download of a
missing issuer certificate, even when the certificate names such addresses).

| Check | Refusal code |
|---|---|
| The operator set `AMR_PDF_TRUST_ROOTS_PATH` to a readable PEM file of at least one certificate | `pdf_trust_roots_missing` |
| The decoded file is at most 8 MiB and carries at most 10 signatures | `pdf_too_large` (or `invalid_input` for an over-long base64 string) |
| The file is a readable PDF | `pdf_unreadable` |
| Its first revision carries `amr-mandate.json`, and the PDF that `prepare_mandate_pdf` builds from that content is, byte for byte, the start of the file (a file rewritten instead of appended to is refused) | `pdf_not_a_mandate` |
| The first revision the reader finds, following `/Prev` back from the end of the file, is that mandate PDF (a second document appended after it is refused) | `pdf_modified` |
| At least one signature | `pdf_not_signed` |
| No document timestamp (`/DocTimeStamp`, PAdES-B-LTA): not checked in this version. A timestamp inside a signature (PAdES-B-T) is accepted but not reported | `document_timestamp_unsupported` |
| The first signature is the first update appended to the mandate PDF (nothing unsigned, such as a signature field prepared in advance, between them) | `pdf_modified` |
| Every revision appended to the mandate PDF only adds signature fields and validation data (pyHanko's standard difference policy, reviewed from the mandate PDF itself, so a page or the attachment changed before the first signature is caught, not only after it) | `pdf_modified` |
| Every signature is intact and cryptographically valid (algorithms pyHanko accepts by default; SHA-1 is refused) | `signature_invalid` |
| Every signature covers the whole file, or its whole revision with only signatures and validation data after it | `pdf_modified` |
| Every signer's certificate chains to one of the trust roots and is valid at the time of the check | `signer_not_trusted` |
| The content is this mandate: for a mandate signed with the principal's Ed25519 key, exactly the bytes it signed; otherwise the principal, agent, scope, legal basis, parent, metadata, duration (to the second) and perimeter (narrowed by the parent's for a sub-mandate), with a `signed_at` within `AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` of the mandate's creation | `pdf_not_this_mandate` |
| The same content was not already recorded for another mandate | `pdf_used_by_another_mandate` |
| The mandate exists | `mandate_not_found` |
| The same signed file was not recorded for this mandate already | `pdf_already_attached` |

Several signatures (for example two directors) are accepted; each must pass every
check, and each is recorded.

## 4. What is recorded

One row of `mandate_pdf_signatures` per (mandate, signed file), append-only:
the mandate's `chain_hash`, `payload_sha256`, `pdf_sha256` (the unsigned mandate PDF),
`signed_pdf_sha256`, the signed file itself, the signers, `trust_roots_sha256` and
`checked_at`. Its `chain_hash` is `compute_hash` of these fields (the file by its
SHA-256) and the previous row's `chain_hash` (`""` for the first), across the table.
A `pdf_signature_attached` event names the signed file's SHA-256 in `mandate_events`.

Each signer: `field_name`, `signer_reported_time` (the time the signing tool wrote;
not a trusted timestamp), `modification_level_after`, and `certificate`:
`subject` and `issuer` (common name, given name, surname, serial number, organisation
name, organisation identifier, country, when present), `certificate_sha256`, `serial`,
`not_valid_before`, `not_valid_after`, `qc_statements` (`qc_compliance`, `qc_sscd`,
`qc_types` among `esign`, `eseal`, `web`) and `declared_level`:

| `declared_level` | The certificate declares (ETSI EN 319 412-5) |
|---|---|
| `qualified_on_qscd` | an EU qualified certificate (QcCompliance) whose key is in a qualified signature or seal creation device (QcSSCD) |
| `qualified` | an EU qualified certificate, without QcSSCD |
| `not_qualified` | neither |

`trust_roots_sha256` is the SHA-256 of the sorted, newline-joined SHA-256 fingerprints
(DER) of the trust roots: it names the exact set of roots the check used.

## 5. Limits (read before relying on a record)

- **Trust roots are the operator's choice.** AMR does not read the EU trusted lists.
  `declared_level` is what the certificate says about itself under these roots; it is
  a qualified signature only if the roots are qualified trust service providers for
  qualified certificates, which is the operator's responsibility (extract them from
  the trusted list of the relevant Member State).
- **No revocation check.** A certificate revoked before the check is not detected
  (`revocation_checked: false` in the result). Re-check the signed file with a
  validation service when it matters.
- **Checked once.** The Proof Pack shows the signatures as checked at `checked_at`, with
  the roots named by `trust_roots_sha256`; it does not re-validate them (a certificate
  may expire later). `pdf_signatures_intact` only says that the records were not
  altered or removed.
- **Signer and principal.** Anyone holding a certificate under the operator's roots can
  sign the PDF and attach it. AMR records who the certificate names; it does not decide
  whether that person is the principal or may act for it (step 3). Compare
  `signers[].certificate.subject` (for an organisation, `organization_identifier`) with
  the principal yourself.
- **Signing tools.** A tool that rewrites the whole file when signing, instead of
  appending the signature, produces a file that is refused (`pdf_not_a_mandate`).
  The mandate PDF declares an empty form with `SigFlags 3` (append only) so that tools
  append.
- **Signing time.** `signer_reported_time` is written by the signing tool; it is not
  compared with the certificate's validity or the mandate's dates. The certificate is
  checked as valid at `checked_at`.
- **Document timestamps.** Files carrying a document timestamp (PAdES-B-LTA, as some
  remote signing services produce) are refused (`document_timestamp_unsupported`).
- **Size.** The signed file is stored in the registry database (at most 8 MiB each).

## 6. Compatibility

Existing mandates, their `chain_hash` and the other tables are unchanged; the new table
is created on start (schema v10). The mandate PDF of `prepare_mandate_pdf` now declares
an empty form (`/AcroForm << /Fields [] /SigFlags 3 >>`), so its bytes and `pdf_sha256`
differ from the version of 06/11/2026 for the same arguments; its attached content and
`payload_sha256` are unchanged. No published release contained `prepare_mandate_pdf`.
New dependency: `pyhanko` (MIT licence), pinned to the 0.38 series.
