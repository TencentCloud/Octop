export interface SkillPackage {
  id: string;
  name: string;
  description: string;
  created_by: string;
  skill_count: number;
  icon_name?: string;
  icon_url?: string;
  created_at: string;
  updated_at: string;
}

export interface SkillPackageSkill {
  slug: string;
  name: string;
  description: string;
  path: string;
  kind: "package";
  package_id: string;
  emoji?: string;
  icon_url?: string;
}

export interface SkillPackageSkillDetail extends SkillPackageSkill {
  frontmatter: Record<string, unknown>;
  body: string;
  raw: string;
}

export interface SkillPackageDetail extends SkillPackage {
  skills: SkillPackageSkill[];
}

export interface CreateSkillPackageBody {
  name: string;
  description?: string;
  icon_name?: string;
  icon_url?: string;
}

export interface UpdateSkillPackageBody {
  name?: string;
  description?: string;
  icon_name?: string;
  icon_url?: string;
}

export interface CreateSkillPackageSkillBody {
  name: string;
  content?: string;
  files?: Array<{ path: string; content_base64: string }>;
  overwrite?: boolean;
}

export interface UpdateSkillPackageSkillBody {
  content?: string;
  files?: Array<{ path: string; content_base64: string }>;
}
