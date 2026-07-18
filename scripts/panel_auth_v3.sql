-- ============================================================================
-- panel_auth_v3.sql — Login del panel en el Supabase v3 (2026-07-18)
-- PEGAR ENTERO en: dashboard Supabase v3 (eoizfjsyejixjzwgzwkt) → SQL Editor → Run
-- Crea: organizations / profiles / agent_configs + onboarding automático al
-- registrarse + RLS. Idempotente (se puede correr 2 veces sin drama).
-- Claude no pudo ejecutarlo por permisos (toca auth.users) — lo corre Lucas.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.organizations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  slug        text UNIQUE NOT NULL,
  timezone    text NOT NULL DEFAULT 'America/Argentina/Jujuy',
  read_only   boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.profiles (
  id               uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  organization_id  uuid REFERENCES public.organizations(id) ON DELETE CASCADE,
  full_name        text,
  role             text NOT NULL DEFAULT 'owner' CHECK (role IN ('owner','staff')),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS profiles_org_idx ON public.profiles(organization_id);

CREATE TABLE IF NOT EXISTS public.agent_configs (
  organization_id  uuid PRIMARY KEY REFERENCES public.organizations(id) ON DELETE CASCADE,
  system_prompt    text NOT NULL,
  tone             text NOT NULL DEFAULT 'profesional y cálido',
  business_info    jsonb NOT NULL DEFAULT '{}'::jsonb,
  services         jsonb NOT NULL DEFAULT '[]'::jsonb,
  business_hours   jsonb NOT NULL DEFAULT '{}'::jsonb,
  collect_is_new_patient boolean NOT NULL DEFAULT true,
  handoff_message  text DEFAULT 'Te paso con un humano en un momento.',
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.current_org_id()
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT organization_id FROM public.profiles WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_org_id uuid; v_base text; v_slug text; v_org_name text;
BEGIN
  v_org_name := coalesce(nullif(trim(new.raw_user_meta_data->>'org_name'), ''), 'Áurea Odontología');
  v_base := lower(regexp_replace(v_org_name, '[^a-zA-Z0-9]+', '-', 'g'));
  v_base := trim(both '-' from v_base);
  IF v_base = '' THEN v_base := 'negocio'; END IF;
  v_slug := v_base || '-' || substr(md5(random()::text || new.id::text), 1, 6);
  INSERT INTO public.organizations (name, slug, read_only)
  VALUES (v_org_name, v_slug, true) RETURNING id INTO v_org_id;
  INSERT INTO public.profiles (id, organization_id, full_name, role)
  VALUES (new.id, v_org_id, nullif(trim(new.raw_user_meta_data->>'full_name'), ''), 'owner');
  INSERT INTO public.agent_configs (organization_id, system_prompt)
  VALUES (v_org_id, 'Asiri — el prompt real vive en n8n; esta config no afecta al bot.');
  RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT, UPDATE ON public.organizations TO authenticated;
GRANT SELECT, UPDATE ON public.profiles TO authenticated;
GRANT SELECT, UPDATE ON public.agent_configs TO authenticated;

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_configs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "org: members can read" ON public.organizations;
CREATE POLICY "org: members can read" ON public.organizations
  FOR SELECT USING (id = public.current_org_id());
DROP POLICY IF EXISTS "profiles: read self or same org" ON public.profiles;
CREATE POLICY "profiles: read self or same org" ON public.profiles
  FOR SELECT USING (id = auth.uid() OR organization_id = public.current_org_id());
DROP POLICY IF EXISTS "agent_configs: own org" ON public.agent_configs;
CREATE POLICY "agent_configs: own org" ON public.agent_configs
  FOR ALL USING (organization_id = public.current_org_id())
  WITH CHECK (organization_id = public.current_org_id());
