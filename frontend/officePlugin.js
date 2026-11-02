import { createReadStream, existsSync, statSync, cpSync } from 'node:fs';
import { resolve, sep, extname } from 'node:path';

export function officePlugin() {
  const root = resolve(import.meta.dirname, '../agents_office/app/static/office');
  const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.json':'application/json','.woff2':'font/woff2','.webp':'image/webp'};
  const middleware = (request, response, next) => {
    if (!request.url?.startsWith('/office')) return next();
    const pathname = decodeURIComponent(request.url.split('?')[0]);
    if (pathname === '/office') { response.writeHead(302, {Location:'/office/'}); response.end(); return; }
    const path = resolve(root, `.${pathname.slice('/office'.length)}`, pathname.endsWith('/') ? 'index.html' : '');
    if (!path.startsWith(root + sep) || !existsSync(path) || !statSync(path).isFile()) return next();
    response.setHeader('Content-Type', types[extname(path)] || 'application/octet-stream');
    createReadStream(path).pipe(response);
  };
  return {name:'nova-office', configureServer(server) {server.middlewares.use(middleware);}, configurePreviewServer(server) {server.middlewares.use(middleware);}, closeBundle() {if(existsSync(root)) cpSync(root, resolve(import.meta.dirname,'dist/office'), {recursive:true});}};
}
