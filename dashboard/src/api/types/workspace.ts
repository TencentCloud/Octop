export interface MdFileInfo {
  filename: string;
  path: string;
  size: number;
  created_time: string;
  modified_time: string;
}

export interface MdFileContent {
  content: string;
}

export interface MarkdownFile extends MdFileInfo {
  updated_at: number;
}

export interface DailyMemoryFile extends MdFileInfo {
  date: string;
  updated_at: number;
}

export interface FileTreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified_time: string;
  children: FileTreeNode[];
}

export interface WorkspaceFileContent {
  name: string;
  path: string;
  content: string;
  size: number;
}
