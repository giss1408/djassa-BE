-- Supabase investor room. Run in the Supabase SQL editor as project owner.
-- Keep this room separate from the demo-user authentication used by Djassa apps.

create extension if not exists pgcrypto;

create table if not exists public.investor_room_members (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text not null,
    organization text,
    active boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists public.investor_room_documents (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    description text not null default '',
    category text not null,
    version text not null,
    file_name text not null,
    storage_path text not null unique,
    required boolean not null default false,
    sort_order integer not null default 0,
    active boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists public.investor_room_permissions (
    user_id uuid not null references public.investor_room_members(user_id) on delete cascade,
    document_id uuid not null references public.investor_room_documents(id) on delete cascade,
    active boolean not null default true,
    granted_at timestamptz not null default now(),
    primary key (user_id, document_id)
);

create table if not exists public.investor_room_metrics (
    id uuid primary key default gen_random_uuid(),
    section_key text not null,
    label text not null,
    numeric_value numeric(20, 2) not null,
    currency text,
    note text,
    sort_order integer not null default 0,
    active boolean not null default true,
    updated_at timestamptz not null default now()
);

create table if not exists public.investor_room_reviews (
    user_id uuid not null references public.investor_room_members(user_id) on delete cascade,
    document_id uuid not null references public.investor_room_documents(id) on delete cascade,
    reviewed boolean not null default false,
    needs_discussion boolean not null default false,
    include_in_pack boolean not null default false,
    updated_at timestamptz not null default now(),
    primary key (user_id, document_id)
);

create table if not exists public.investor_room_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.investor_room_members(user_id) on delete cascade,
    event_type text not null check (event_type in ('document_download', 'review_update')),
    document_id uuid references public.investor_room_documents(id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists investor_room_permissions_document_idx
    on public.investor_room_permissions (document_id, user_id) where active;
create index if not exists investor_room_documents_order_idx
    on public.investor_room_documents (sort_order) where active;
create index if not exists investor_room_metrics_order_idx
    on public.investor_room_metrics (section_key, sort_order) where active;
create index if not exists investor_room_events_user_idx
    on public.investor_room_events (user_id, created_at desc);

create or replace function public.investor_room_is_active()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(
        (select auth.jwt() ->> 'aal') = 'aal2'
        and exists (
            select 1
            from public.investor_room_members m
            where m.user_id = (select auth.uid())
              and m.active
        ),
        false
    );
$$;

create or replace function public.investor_room_can_read_document(target_document_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(
        public.investor_room_is_active()
        and exists (
            select 1
            from public.investor_room_permissions p
            join public.investor_room_documents d on d.id = p.document_id
            where p.user_id = (select auth.uid())
              and p.document_id = target_document_id
              and p.active
              and d.active
        ),
        false
    );
$$;

create or replace function public.investor_room_can_read_path(target_path text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(
        exists (
            select 1
            from public.investor_room_documents d
            where d.storage_path = target_path
              and public.investor_room_can_read_document(d.id)
        ),
        false
    );
$$;

revoke all on function public.investor_room_is_active() from public, anon;
revoke all on function public.investor_room_can_read_document(uuid) from public, anon;
revoke all on function public.investor_room_can_read_path(text) from public, anon;
grant execute on function public.investor_room_is_active() to authenticated, service_role;
grant execute on function public.investor_room_can_read_document(uuid) to authenticated, service_role;
grant execute on function public.investor_room_can_read_path(text) to authenticated, service_role;

alter table public.investor_room_members enable row level security;
alter table public.investor_room_documents enable row level security;
alter table public.investor_room_permissions enable row level security;
alter table public.investor_room_metrics enable row level security;
alter table public.investor_room_reviews enable row level security;
alter table public.investor_room_events enable row level security;

revoke all on public.investor_room_members from public, anon, authenticated;
revoke all on public.investor_room_documents from public, anon, authenticated;
revoke all on public.investor_room_permissions from public, anon, authenticated;
revoke all on public.investor_room_metrics from public, anon, authenticated;
revoke all on public.investor_room_reviews from public, anon, authenticated;
revoke all on public.investor_room_events from public, anon, authenticated;

grant select on public.investor_room_members to authenticated;
grant select on public.investor_room_documents to authenticated;
grant select on public.investor_room_metrics to authenticated;
grant select, insert, update on public.investor_room_reviews to authenticated;
grant insert on public.investor_room_events to authenticated;

drop policy if exists investor_room_member_reads_self on public.investor_room_members;
create policy investor_room_member_reads_self
    on public.investor_room_members for select to authenticated
    using (user_id = (select auth.uid()) and public.investor_room_is_active());

drop policy if exists investor_room_read_assigned_documents on public.investor_room_documents;
create policy investor_room_read_assigned_documents
    on public.investor_room_documents for select to authenticated
    using (active and public.investor_room_can_read_document(id));

drop policy if exists investor_room_read_metrics on public.investor_room_metrics;
create policy investor_room_read_metrics
    on public.investor_room_metrics for select to authenticated
    using (active and public.investor_room_is_active());

drop policy if exists investor_room_read_own_reviews on public.investor_room_reviews;
create policy investor_room_read_own_reviews
    on public.investor_room_reviews for select to authenticated
    using (user_id = (select auth.uid()) and public.investor_room_can_read_document(document_id));

drop policy if exists investor_room_create_own_reviews on public.investor_room_reviews;
create policy investor_room_create_own_reviews
    on public.investor_room_reviews for insert to authenticated
    with check (user_id = (select auth.uid()) and public.investor_room_can_read_document(document_id));

drop policy if exists investor_room_update_own_reviews on public.investor_room_reviews;
create policy investor_room_update_own_reviews
    on public.investor_room_reviews for update to authenticated
    using (user_id = (select auth.uid()) and public.investor_room_can_read_document(document_id))
    with check (user_id = (select auth.uid()) and public.investor_room_can_read_document(document_id));

drop policy if exists investor_room_log_own_events on public.investor_room_events;
create policy investor_room_log_own_events
    on public.investor_room_events for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and public.investor_room_is_active()
        and (document_id is null or public.investor_room_can_read_document(document_id))
    );

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'investor-room',
    'investor-room',
    false,
    52428800,
    array[
        'application/pdf',
        'text/markdown',
        'text/plain',
        'text/csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists investor_room_read_assigned_files on storage.objects;
create policy investor_room_read_assigned_files
    on storage.objects for select to authenticated
    using (
        bucket_id = 'investor-room'
        and public.investor_room_can_read_path(name)
    );