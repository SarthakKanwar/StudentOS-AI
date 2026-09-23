-- StudentOS — initial schema
--
-- Source of truth: architecture.md §8 (data model), §8.1 (field semantics),
-- §6.1 (document status lifecycle), security.md §3 (RLS).
--
-- Apply with: Supabase Studio → SQL Editor, or `supabase db push`.
-- This file is committed and is the only place the schema is defined.

-- pgvector. ADR-004 chose Supabase + pgvector over a separate vector service so
-- that approval filtering is a SQL join rather than an index-sync problem.
create extension if not exists vector;


-- ─────────────────────────────────────────────────────────────── documents ──

create table if not exists documents (
    id                  uuid primary key default gen_random_uuid(),

    -- §8.1: title is the human-readable name shown in citations.
    -- original_filename is what was uploaded, kept for provenance only.
    title               text        not null,
    original_filename   text        not null,

    storage_path        text,

    -- §8.1: SHA-256 of the uploaded bytes — integrity and deduplication.
    -- Not a version identifier; versioning is FR-2.11 (V2).
    file_hash           text        not null,

    uploaded_by         uuid        references auth.users (id) on delete set null,

    -- §6.1: the ONLY field that determines retrievability. There is
    -- deliberately no separate `approved` boolean.
    status              text        not null default 'uploaded',

    -- Audit metadata only. These never gate retrieval, and are retained after
    -- revocation as a record of the prior approval.
    approved_by         uuid        references auth.users (id) on delete set null,
    approved_at         timestamptz,

    page_count          integer     not null default 0,

    -- §8.1: the column exists from M1 so no migration is needed later, but
    -- nothing sets it until the V2 scanner ships (FR-3.6). Always false for now.
    injection_risk_flag boolean     not null default false,

    error_message       text,
    created_at          timestamptz not null default now(),

    constraint documents_status_valid
        check (status in ('uploaded', 'processing', 'ready', 'approved', 'failed')),

    -- A failed document must say why; a non-failed one must not carry a reason.
    -- FR-2.10 requires a readable failure reason, and this stops a half-ingested
    -- document being left in a state that looks healthy.
    constraint documents_error_message_matches_status
        check (
            (status = 'failed' and error_message is not null)
            or (status <> 'failed' and error_message is null)
        ),

    constraint documents_approved_has_audit
        check (status <> 'approved' or approved_at is not null),

    constraint documents_page_count_non_negative
        check (page_count >= 0)
);

create index if not exists documents_status_idx    on documents (status);
create index if not exists documents_file_hash_idx on documents (file_hash);


-- ────────────────────────────────────────────────────────────────── chunks ──

create table if not exists chunks (
    -- §8.1: canonical `c_<short>` id, deterministic within one ingestion.
    id            text        primary key,

    document_id   uuid        not null references documents (id) on delete cascade,

    content       text        not null,

    -- §8.1: 1-BASED page numbers. A chunk MAY span a page boundary, in which
    -- case page_start < page_end and a citation renders the range.
    page_start    integer,
    page_end      integer,

    chunk_index   integer     not null,
    char_start    integer     not null,
    char_end      integer     not null,

    -- §8.1: NULL unless a heading was reliably detected. A guessed label would
    -- appear in a citation as false precision.
    section_label text,

    -- Counted with tiktoken / cl100k_base, per config/retrieval.yaml.
    token_count   integer     not null,

    created_at    timestamptz not null default now(),

    constraint chunks_id_format          check (id like 'c\_%'),
    constraint chunks_pages_are_1_based  check (page_start is null or page_start >= 1),
    constraint chunks_page_range_ordered check (
        page_start is null or page_end is null or page_end >= page_start
    ),
    constraint chunks_offsets_ordered    check (char_end >= char_start),
    constraint chunks_index_non_negative check (chunk_index >= 0),
    constraint chunks_unique_position    unique (document_id, chunk_index)
);

create index if not exists chunks_document_id_idx on chunks (document_id);

-- Full-text index, for the keyword half of hybrid retrieval in M2.
create index if not exists chunks_content_fts_idx
    on chunks using gin (to_tsvector('english', content));


-- ─────────────────────────────────────────────────────── chunk_embeddings ──

-- Split from `chunks` so that re-embedding with a different model does not
-- rewrite content rows, and so a plain SELECT on chunks does not drag 1,536
-- floats per row (architecture.md §8).
create table if not exists chunk_embeddings (
    chunk_id      text        primary key references chunks (id) on delete cascade,

    -- 1536 verified against the live text-embedding-3-small deployment
    -- (architecture.md §10.1). Do not change without re-ingesting the corpus.
    embedding     vector(1536) not null,

    -- Which deployment produced this vector; lets a stale re-embed be detected.
    model_version text        not null,

    created_at    timestamptz not null default now()
);

-- HNSW for approximate nearest-neighbour search. Cosine distance, matching the
-- similarity thresholds in config/retrieval.yaml (tau_min / tau_support).
-- m and ef_construction are pgvector defaults, ample at NFR-10 scale.
create index if not exists chunk_embeddings_hnsw_idx
    on chunk_embeddings using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);


-- ──────────────────────────────────────────────────── row level security ──

-- The backend connects with the service role, which bypasses RLS entirely.
-- These policies therefore govern the anon/authenticated (student) path, and
-- enforce the core product guarantee: a student can only ever read content from
-- a document an admin has approved.

alter table documents        enable row level security;
alter table chunks           enable row level security;
alter table chunk_embeddings enable row level security;

-- Students may list approved documents, and nothing else. Documents that are
-- uploaded, processing, ready or failed are invisible to them.
drop policy if exists documents_select_approved on documents;
create policy documents_select_approved
    on documents for select
    to authenticated
    using (status = 'approved');

-- Students may read a chunk only when its parent document is approved.
-- Revocation (approved → ready) therefore takes effect immediately, with no
-- re-indexing, which is what FR-2.9 requires.
drop policy if exists chunks_select_approved on chunks;
create policy chunks_select_approved
    on chunks for select
    to authenticated
    using (
        exists (
            select 1 from documents d
            where d.id = chunks.document_id
              and d.status = 'approved'
        )
    );

-- Embeddings are never served to the client. No select policy is granted, so
-- with RLS enabled and no policy the table is unreadable to authenticated
-- users; only the service role can reach it.

-- No insert/update/delete policies are defined for any of these tables:
-- all writes go through the backend service role. Ingestion is not a
-- client-side operation.

-- NOTE — admin policies are deliberately absent. They require a decision on
-- where the student/admin role lives (a JWT claim, or a profiles table), which
-- belongs with the admin console in M5. Until then, admin actions run through
-- the backend service role. See project-plan.md issue 3.
