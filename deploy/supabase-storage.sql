-- New app-specific objects only. Existing authentication/users are untouched.
begin;
create table if not exists public.dataneat_files (
  id uuid primary key,
  owner uuid not null references auth.users(id) on delete cascade,
  session text not null,
  metadata jsonb not null,
  payload text not null,
  expires_at double precision,
  updated_at timestamptz not null default now()
);
alter table public.dataneat_files enable row level security;
revoke all on public.dataneat_files from public, anon, authenticated;
grant select, insert, update, delete on public.dataneat_files to service_role;
create index if not exists dataneat_files_owner on public.dataneat_files(owner);
create index if not exists dataneat_files_expiry on public.dataneat_files(expires_at);

create or replace function public.dataneat_commit_file(
 p_id uuid, p_owner uuid, p_session text, p_metadata jsonb,
 p_payload text, p_expires double precision
) returns void language plpgsql security invoker set search_path = '' as $$
declare existing_owner uuid;
begin
 perform pg_catalog.pg_advisory_xact_lock(62418937);
 select owner into existing_owner from public.dataneat_files where id = p_id;
 if existing_owner is not null and existing_owner <> p_owner then
   raise exception 'DATANEAT_OWNER';
 end if;
 -- Hard caps keep this early beta comfortably inside the free database budget.
 if octet_length(p_payload) > 10*1024*1024
 or (select coalesce(sum(octet_length(payload)),0) from public.dataneat_files where id <> p_id) + octet_length(p_payload) > 150*1024*1024
 or (select coalesce(sum(octet_length(payload)),0) from public.dataneat_files where owner=p_owner and id <> p_id) + octet_length(p_payload) > 20*1024*1024
 or (select count(*) from public.dataneat_files where owner=p_owner and id <> p_id) >= 20 then
   raise exception 'DATANEAT_QUOTA';
 end if;
 insert into public.dataneat_files(id,owner,session,metadata,payload,expires_at)
 values(p_id,p_owner,p_session,p_metadata,p_payload,p_expires)
 on conflict(id) do update set metadata=excluded.metadata,payload=excluded.payload,
 expires_at=excluded.expires_at,updated_at=now();
end;
$$;
revoke all on function public.dataneat_commit_file(uuid,uuid,text,jsonb,text,double precision) from public, anon, authenticated;
grant execute on function public.dataneat_commit_file(uuid,uuid,text,jsonb,text,double precision) to service_role;
commit;
