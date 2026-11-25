import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

// A repository workflow check: run from the checked-out source, not the
// temporary frontend copy used for Next's export.
const workflow=fs.readFileSync(new URL('../../../../.github/workflows/efhc-pages.yml',import.meta.url),'utf8');
function input(stepName,key,fallback){
 const step=workflow.split(`      - name: ${stepName}\n`)[1]?.split('\n      - name: ')[0];
 assert.ok(step,stepName+' must remain in the publication workflow');
 const value=step.match(new RegExp(`^          ${key}: (.+)$`,'m'))?.[1].trim();
 return value?.replace(/^['"]|['"]$/g,'')||fallback;
}

const jobs=workflow.split(/^  (?=[a-z]+:\s*$)/m);
const build=jobs.find(s=>s.startsWith('build:\n'));
const publish=jobs.find(s=>s.startsWith('publish:\n'));

test('Pages selects exactly the artifact from the successful build, even after retrying only publish',()=>{
 assert.ok(build && publish,'a failed publish must be retryable independently');
 assert.match(publish,/^    needs: build$/m);
 const retained='${{ steps.bundle.outputs.artifact_name }}';
 assert.ok(build.includes('artifact_name: '+retained),'build must expose the upload name');
 assert.ok(build.includes('artifact_id: ${{ steps.upload.outputs.artifact_id }}'));
 assert.equal(input('Upload compiled React to Pages','name','github-pages'),retained);
 assert.equal(input('Deploy real React to GitHub Pages','artifact_name','github-pages'),
  '${{ needs.build.outputs.artifact_name }}');
 const format=build.match(/artifact_name=(github-pages-%s-%s)\\n' \\\n\s*"\$build_commit" "\$GITHUB_RUN_ATTEMPT" "\$GITHUB_RUN_ID" "\$GITHUB_RUN_ATTEMPT"/);
 assert.ok(format,'upload name must use its original run ID and build attempt');
 for(const runId of ['41874108310','41874108311']){
  const artifacts=[];
  for(let buildAttempt=1;buildAttempt<=3;buildAttempt++){
   const retainedName=format[1].replace('%s',runId).replace('%s',String(buildAttempt));
   artifacts.push({name:retainedName,buildAttempt});
   for(const deployAttempt of [buildAttempt,buildAttempt+1]){
    const selected=artifacts.filter(a=>a.name===retainedName);
    assert.equal(selected.length,1,'ambiguous artifact at deploy attempt '+deployAttempt);
    assert.equal(selected[0].buildAttempt,buildAttempt);
   }
  }
 }
});
