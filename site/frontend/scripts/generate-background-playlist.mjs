import { readdirSync, statSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const directory = fileURLToPath(new URL('../public/audio/background/', import.meta.url));
const tracks = readdirSync(directory).filter(name => /\.(mp3|ogg|wav|m4a|aac|flac|opus)$/i.test(name));
if (tracks.length !== 1 || tracks[0] !== '1.mp3' || !statSync(join(directory, '1.mp3')).isFile()) {
  throw new Error('Expected the single canonical background track 1.mp3');
}
writeFileSync(join(directory, 'playlist.json'), JSON.stringify(tracks, null, 2) + '\n');
