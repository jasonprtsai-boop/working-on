export function installFakeDom() {
  const elementsById = new Map();

  class FakeClassList {
    constructor() {
      this._set = new Set();
    }
    add(...names) { names.forEach(n => this._set.add(n)); }
    remove(...names) { names.forEach(n => this._set.delete(n)); }
    contains(name) { return this._set.has(name); }
    toString() { return Array.from(this._set).join(' '); }
  }

  class FakeElement {
    constructor(tagName) {
      this.tagName = tagName.toLowerCase();
      this.children = [];
      this.parentNode = null;
      this.dataset = {};
      this.style = {};
      this._listeners = new Map();
      this.classList = new FakeClassList();
      this._className = '';
      this._textContent = '';
      this.id = '';
      this.attributes = {};
    }

    get parentElement() { return this.parentNode; }

    set className(v) {
      this._className = String(v || '');
      this.classList = new FakeClassList();
      this._className.split(/\s+/).filter(Boolean).forEach(c => this.classList.add(c));
    }
    get className() { return this._className; }

    set textContent(v) { this._textContent = String(v ?? ''); }
    get textContent() {
      if (this._textContent) return this._textContent;
      if (this.tagName === 'span') return this._textContent;
      return this.children.map(c => c.textContent).join('');
    }

    set innerText(v) { this.textContent = v; }
    get innerText() { return this.textContent; }

    set innerHTML(html) {
      this.children = [];
      const m = String(html || '').match(/<span>([\s\S]*)<\/span>/i);
      if (m) {
        const span = new FakeElement('span');
        span.textContent = m[1];
        this.appendChild(span);
      }
    }

    appendChild(child) {
      if (child.tagName === '#document-fragment') {
        child.children.slice().forEach(grandchild => this.appendChild(grandchild));
        child.children = [];
        return child;
      }
      child.parentNode = this;
      this.children.push(child);
      if (child.id) elementsById.set(child.id, child);
      return child;
    }

    append(...children) {
      children.forEach(child => this.appendChild(child));
    }

    prepend(child) {
      child.parentNode = this;
      this.children.unshift(child);
      if (child.id) elementsById.set(child.id, child);
      return child;
    }

    remove() {
      if (!this.parentNode) return;
      const idx = this.parentNode.children.indexOf(this);
      if (idx >= 0) this.parentNode.children.splice(idx, 1);
      this.parentNode = null;
    }

    replaceChildren(...children) {
      this.children.forEach(child => { child.parentNode = null; });
      this.children = [];
      this._textContent = '';
      children.forEach(child => this.appendChild(child));
    }

    addEventListener(type, handler) {
      if (!this._listeners.has(type)) this._listeners.set(type, []);
      this._listeners.get(type).push(handler);
    }

    setPointerCapture() {}

    setAttribute(name, value) {
      this.attributes[name] = String(value);
    }

    getAttribute(name) {
      return this.attributes[name];
    }

    querySelectorAll(selector) {
      const sel = String(selector || '').trim();
      const match = (el) => {
        if (sel === 'span') return el.tagName === 'span';
        if (!sel.startsWith('.')) return false;
        const classes = sel.split('.').filter(Boolean);
        return classes.every(c => el.classList.contains(c));
      };

      const out = [];
      const walk = (node) => {
        for (const child of node.children) {
          if (match(child)) out.push(child);
          walk(child);
        }
      };
      walk(this);
      return out;
    }

    querySelector(selector) {
      return this.querySelectorAll(selector)[0] || null;
    }

    getBoundingClientRect() {
      return { width: 1000, height: 1000, left: 0, top: 0 };
    }
  }

  global.document = {
    body: new FakeElement('body'),
    createElement: (tag) => new FakeElement(tag),
    createElementNS: (_ns, tag) => new FakeElement(tag),
    createDocumentFragment: () => new FakeElement('#document-fragment'),
    getElementById: (id) => elementsById.get(id) || null,
    querySelectorAll: (selector) => global.document.body.querySelectorAll(selector),
    querySelector: (selector) => global.document.body.querySelector(selector),
    addEventListener: () => {},
    removeEventListener: () => {}
  };

  global.window = {
    state: { isPaused: false, isEmergency: false },
    scrollTo: () => {}
  };
  global.requestAnimationFrame = (callback) => callback();
  global.cancelAnimationFrame = () => {};
  global.window.requestAnimationFrame = global.requestAnimationFrame;
  global.window.cancelAnimationFrame = global.cancelAnimationFrame;

  return { elementsById, FakeElement };
}

export function setupContainer(id, parent = document.body) {
  const container = document.createElement('div');
  container.id = id;
  parent.appendChild(container);
  return container;
}
