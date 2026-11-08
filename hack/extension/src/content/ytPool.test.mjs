import { strict as assert } from 'node:assert';
const { parseYtInitialData } = await import('../../dist_test/content/ytPool.js');
const html = `<script>var ytInitialData = ${JSON.stringify({
  a: { videoRenderer: { videoId: "abc123X", title: { runs: [{ text: "Escalade bloc" }] },
       ownerText: { runs: [{ text: "GrimpeurFR" }] }, thumbnail: { thumbnails: [{ url: "t1" }, { url: "t2" }] },
       lengthText: { simpleText: "8:24" }, viewCountText: { simpleText: "12 k" } } },
  b: { lockupViewModel: { videoId: "zz99", metadata: { lockupMetadataViewModel: { title: { content: "Ramen recette" } } },
       contentImage: { thumbnailViewModel: { image: { sources: [{ url: "th" }] } } } } },
  c: { shortsLockupViewModel: { videoId: "sh77", overlayMetadata: { primaryText: { content: "short drama" } },
       thumbnail: { sources: [{ url: "s1" }] } } },
})};</script>`;
const vids = parseYtInitialData(html);
assert.equal(vids.length, 3);
assert.equal(vids.find(v => v.id === "abc123X").kind, "video");
assert.equal(vids.find(v => v.id === "abc123X").title, "Escalade bloc");
assert.equal(vids.find(v => v.id === "sh77").kind, "short");
assert.equal(parseYtInitialData("<html>nothing</html>").length, 0);
console.log("parser tests ok");
