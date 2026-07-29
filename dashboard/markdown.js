/* Markdown -> DOM, for rendering ledger artifacts (spec.md, review.md, qa.md).
 *
 * Deliberately NOT a CommonMark implementation. It covers what the task
 * library actually emits — headings, paragraphs, lists, fenced code, block
 * quotes, rules, pipe tables, and inline code/emphasis/links/images — and
 * ignores the rest, rendering unknown syntax as the literal text it is.
 *
 * # ponytail: subset parser, ~250 lines. The obvious alternative is marked or
 * # markdown-it, and the reason neither is here is that both produce an HTML
 * # STRING, which can only be mounted with innerHTML — forbidden outright
 * # (docs/dashboard-design-requirements.md §4.4), because artifact content is
 * # written by agents and is the least trusted data on the page. This builds
 * # DOM nodes directly, so there is no parse step that could emit markup: a
 * # `<script>` in a spec is text, always. If the subset ever proves too thin,
 * # the upgrade is a real parser plus DOMPurify, not innerHTML plus hope.
 */
window.AgentHqMarkdown = (function () {
  'use strict';

  var HEADING = /^(#{1,6})\s+(.*)$/;
  var FENCE = /^\s*(```|~~~)(.*)$/;
  var RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
  var QUOTE = /^\s*>\s?(.*)$/;
  var ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  var TABLE_SEP = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/;

  /* Inline: code first (its content is literal), then images, links,
     strong, em. Anything unmatched stays text. */
  var INLINE = new RegExp([
    '`([^`]+)`',
    '!\\[([^\\]]*)\\]\\(([^)\\s]+)\\)',
    '\\[([^\\]]*)\\]\\(([^)\\s]+)\\)',
    '\\*\\*([^*]+)\\*\\*',
    '__([^_]+)__',
    '\\*([^*\\n]+)\\*',
    '(?:^|(?<=\\W))_([^_\\n]+)_(?=\\W|$)'
  ].join('|'), 'g');

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /* `resolve` turns a markdown href into a URL we are willing to link, or
     null. Everything it rejects renders as plain text — a `javascript:` link
     in an artifact becomes visible characters, never a live anchor. */
  function inline(text, resolve, into) {
    var last = 0, m;
    INLINE.lastIndex = 0;
    while ((m = INLINE.exec(text)) !== null) {
      if (m.index > last) into.appendChild(document.createTextNode(text.slice(last, m.index)));
      last = INLINE.lastIndex;

      if (m[1] !== undefined) {
        into.appendChild(el('code', 'md-code', m[1]));
      } else if (m[2] !== undefined || m[3] !== undefined) {
        var src = resolve(m[3], 'image');
        if (src) {
          var img = el('img', 'md-img');
          img.src = src;
          img.alt = m[2] || '';
          img.loading = 'lazy';
          into.appendChild(img);
        } else {
          into.appendChild(el('span', 'md-broken', m[2] ? m[2] + ' (' + m[3] + ')' : m[3]));
        }
      } else if (m[4] !== undefined || m[5] !== undefined) {
        var href = resolve(m[5], 'link');
        if (href) {
          var a = el('a', null, m[4] || m[5]);
          a.href = href;
          a.rel = 'noopener noreferrer';
          into.appendChild(a);
        } else {
          into.appendChild(document.createTextNode((m[4] || '') + ' (' + m[5] + ')'));
        }
      } else if (m[6] !== undefined || m[7] !== undefined) {
        into.appendChild(el('strong', null, m[6] !== undefined ? m[6] : m[7]));
      } else if (m[8] !== undefined || m[9] !== undefined) {
        into.appendChild(el('em', null, m[8] !== undefined ? m[8] : m[9]));
      }
    }
    if (last < text.length) into.appendChild(document.createTextNode(text.slice(last)));
    return into;
  }

  function splitRow(line) {
    return line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(function (c) {
      return c.trim();
    });
  }

  function render(text, resolve) {
    var out = document.createDocumentFragment();
    var lines = String(text == null ? '' : text).split(/\r?\n/);
    var i = 0;

    function listBlock(depth) {
      var m0 = ITEM.exec(lines[i]);
      var ordered = /\d/.test(m0[2]);
      var list = el(ordered ? 'ol' : 'ul', 'md-list');
      while (i < lines.length) {
        var m = ITEM.exec(lines[i]);
        if (!m) break;
        var indent = m[1].length;
        if (indent < depth) break;
        if (indent > depth) {
          var nested = listBlock(indent);
          if (list.lastChild) list.lastChild.appendChild(nested);
          else list.appendChild(nested);
          continue;
        }
        var li = el('li');
        inline(m[3], resolve, li);
        list.appendChild(li);
        i++;
      }
      return list;
    }

    while (i < lines.length) {
      var line = lines[i];

      if (!line.trim()) { i++; continue; }

      var fence = FENCE.exec(line);
      if (fence) {
        var body = [];
        i++;
        while (i < lines.length && !FENCE.test(lines[i])) body.push(lines[i++]);
        i++; // closing fence (or EOF)
        var pre = el('pre', 'md-pre');
        pre.appendChild(el('code', null, body.join('\n')));
        out.appendChild(pre);
        continue;
      }

      var heading = HEADING.exec(line);
      if (heading) {
        out.appendChild(inline(heading[2], resolve, el('h' + heading[1].length, 'md-h')));
        i++;
        continue;
      }

      if (RULE.test(line)) { out.appendChild(el('hr', 'md-hr')); i++; continue; }

      if (QUOTE.test(line)) {
        var quoted = [];
        while (i < lines.length && QUOTE.test(lines[i])) quoted.push(QUOTE.exec(lines[i++])[1]);
        var bq = el('blockquote', 'md-quote');
        bq.appendChild(render(quoted.join('\n'), resolve));
        out.appendChild(bq);
        continue;
      }

      // A pipe table is a header row whose NEXT line is the |---|---| rule.
      if (line.indexOf('|') !== -1 && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
        var table = el('table', 'md-table');
        var thead = el('thead');
        var hrow = el('tr');
        splitRow(line).forEach(function (c) { hrow.appendChild(inline(c, resolve, el('th'))); });
        thead.appendChild(hrow);
        table.appendChild(thead);
        i += 2;
        var tbody = el('tbody');
        while (i < lines.length && lines[i].indexOf('|') !== -1 && lines[i].trim()) {
          var row = el('tr');
          splitRow(lines[i++]).forEach(function (c) { row.appendChild(inline(c, resolve, el('td'))); });
          tbody.appendChild(row);
        }
        table.appendChild(tbody);
        var scroller = el('div', 'md-table-scroll');
        scroller.appendChild(table);
        out.appendChild(scroller);
        continue;
      }

      if (ITEM.test(line)) { out.appendChild(listBlock(ITEM.exec(line)[1].length)); continue; }

      var para = [];
      while (i < lines.length && lines[i].trim() && !HEADING.test(lines[i]) &&
             !FENCE.test(lines[i]) && !RULE.test(lines[i]) && !ITEM.test(lines[i]) &&
             !QUOTE.test(lines[i])) {
        para.push(lines[i++]);
      }
      out.appendChild(inline(para.join(' '), resolve, el('p', 'md-p')));
    }
    return out;
  }

  return { render: render };
})();
