/** Local browser verification always targets the actual configured project prefix. */
export function localPagesBase(input = process.env.EFHC_REACT_URL || 'http://127.0.0.1:19240/Test-3/') {
  const url = new URL(input);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.username || url.password || url.search || url.hash ||
      !/^\/[A-Za-z0-9_.-]+\/$/.test(url.pathname) || ['/./','/../'].includes(url.pathname)) {
    throw new Error('Browser verification needs an exact local project Pages URL');
  }
  return url.href;
}
