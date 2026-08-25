import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';


function looksLikeUnityProject(candidate) {
  return fs.existsSync(path.join(candidate, 'Assets'))
    && fs.existsSync(path.join(candidate, 'ProjectSettings', 'ProjectVersion.txt'));
}


export function resolveRepo() {
  if (process.env.BLASTGAME_REPO) {
    return path.resolve(process.env.BLASTGAME_REPO);
  }
  const here = path.dirname(fileURLToPath(import.meta.url));
  const checkout = path.resolve(here, '..', '..', '..');
  const documents = path.join(os.homedir(), 'Documents', 'BlastGame');
  if (looksLikeUnityProject(checkout)) return checkout;
  if (looksLikeUnityProject(documents)) return path.resolve(documents);
  return checkout;
}


export function repoModuleUrl(repo, relativePath) {
  return pathToFileURL(path.join(repo, ...relativePath.split('/'))).href;
}
