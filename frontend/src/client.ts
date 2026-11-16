export type Account = { uid: string; name: string; role: string; dept: string };
export type Person = Account & { epoch: number; model: string };
export type Demo = {
  accounts: Account[];
  password: string;
  departments: string[];
};
export type Doc = {
  id: string;
  title: string;
  dept: string;
  owner: string;
  version: number;
  acl_version: number;
  public: number;
  departments?: string[];
  users?: string[];
  reason: string;
};
export type Ref = {
  id: string;
  doc: string;
  version: number;
  acl_version: number;
  page: number;
  start: number;
  end: number;
  title: string;
  body?: string;
};
export type Answer = {
  id: string;
  answer: string;
  refs: Ref[];
  cached: boolean;
  epoch: number;
  ms: number;
  model: string;
};
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-RAG-Request": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.detail || "请求失败");
  return data as T;
}
export async function uploadData(file: File) {
  if (file.size > 2 * 1024 * 1024) throw Error("文件超过 2 MiB");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 32768)
    binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
  return { filename: file.name, content_b64: btoa(binary) };
}
