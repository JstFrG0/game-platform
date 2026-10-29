<script setup>
import "../focusFeedback.js";
import { computed, nextTick, onBeforeUnmount, provide, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import CoverImage from "../components/CoverImage.vue";
import FilterHelp from "../components/FilterHelp.vue";
import PageJump from "../components/PageJump.vue";
import FilterSpace from "../components/FilterSpace.vue";
import { createFilterSpace, filterSpaceKey } from "../filterSpace.js";
import YearPicker from "../components/YearPicker.vue";
import PlatformPicker from "../components/PlatformPicker.vue";
import GenrePicker from "../components/GenrePicker.vue";
import ModePicker from "../components/ModePicker.vue";
import { request, score } from "../api.js";
import { loadFilterOptions } from "../filterOptions.js";
import { retryCatalogStartup } from "../catalogStartup.js";
import {
  buildCatalogQuery, buildQuery, defaults, listParams,
  makeBrowseState, readBrowseState, readQuery,
} from "../catalog.js";
import { catalogScroll } from "../catalogScroll.js";
import { dissolveSearchText } from "../searchDissolve.js";
import { catalogDataVersion } from "../dataVersion.js";
import { shouldRefreshCatalog } from "../dataUpdateStatus.js";
import { useBlankSelectionClear } from "../blankSelection.js";

const route = useRoute(),
  router = useRouter();

let cardPointerStart = null;
useBlankSelectionClear();
function startCardSelection(event) {
  cardPointerStart = event.button === 0
    ? { grid: event.currentTarget, x: event.clientX, y: event.clientY }
    : null;
}
function guardCardSelection(event) {
  const start = cardPointerStart;
  cardPointerStart = null;
  if (!start || event.detail === 0 || start.grid !== event.currentTarget) return;
  if (Math.hypot(event.clientX - start.x, event.clientY - start.y) < 4) return;
  // A drag anywhere in the grid is a selection gesture, including the cover
  // and gaps between cards. Only a stationary click should open a detail page.
  event.preventDefault();
}
const filters = reactive(readQuery(route.query).filters);
const filterSpace = createFilterSpace(commitSpace);
provide(filterSpaceKey, filterSpace);
let alive = true;
const catalogReady = ref(false), listReady = ref(false), optionsReady = ref(false);
const browseState = ref(readBrowseState(route.query.browse));
const result = ref(null),
  options = ref(null),
  loading = ref(true),
  error = ref(""),
  optionError = ref("");
const filtersOpen = ref(false);
const searchInput = ref(null);
let stopSearchDissolve = () => {};
let listController;
const typeOptions = computed(() =>
  (options.value?.game_types ?? []).filter(t => filters.scope === 'all' ||
    (filters.scope === 'unknown' ? t.key === 'unknown' : t.default_visible)),
);
const yearOptions = computed(() =>
  [
    ...new Set([
      Number(filters.year),
      ...(options.value?.available_years ?? []),
    ]),
  ].sort((a, b) => b - a),
);
const committed = computed(() => readQuery(route.query).filters);
const hasSearch = computed(() => Boolean(committed.value.q.trim()));
const globalSearch = computed(() => hasSearch.value && committed.value.search_scope === "global");
const currentPage = computed(() => readQuery(route.query).page);
const pageNumbers = computed(() => {
  const total = result.value?.total_pages ?? 0,
    current = currentPage.value;
  return [...new Set([1, current - 1, current, current + 1, total])]
    .filter((n) => n >= 1 && n <= total)
    .sort((a, b) => a - b);
});
const number = (n) => (typeof n === "number" ? n.toLocaleString("zh-CN") : "—");

async function loadList(initial = false) {
  listController?.abort();
  const controller = (listController = new AbortController());
  const path = route.fullPath;
  loading.value = true;
  if (!catalogReady.value) listReady.value = false;
  error.value = "";
  const state = readQuery(route.query);
  Object.assign(filters, state.filters);
  browseState.value = readBrowseState(route.query.browse);
  try {
    const fetchList = () => request(
      "games",
      listParams(state.filters, state.page),
      controller.signal,
    );
    const data = initial===true ? await retryCatalogStartup(fetchList,{signal:controller.signal}) : await fetchList();
    if (!controller.signal.aborted && listController === controller) { result.value = data; listReady.value = true; }
  } catch (e) {
    if (
      !controller.signal.aborted &&
      listController === controller &&
      e.name !== "AbortError"
    )
      error.value = e.message;
  } finally {
    if (listController === controller) {
      loading.value = false;
      await nextTick();
      if (!controller.signal.aborted && catalogReady.value) catalogScroll.catalogReady(path);
    }
  }
}

let optionGeneration = 0;
async function loadOptions(initial = false) {
  const generation = ++optionGeneration;
  optionError.value = "";
  filterSpace.state.loading = true;
  filterSpace.state.error = '';
  try {
    const data = initial===true ? await retryCatalogStartup(loadFilterOptions) : await loadFilterOptions();
    if (alive && generation === optionGeneration) { options.value = data; scopeChanged(); optionsReady.value = true; }
  } catch (e) {
    if (alive && generation === optionGeneration) {
      optionError.value = e.message;
      filterSpace.state.error = '筛选选项载入失败';
    }
  } finally {
    if (alive && generation === optionGeneration) filterSpace.state.loading = false;
  }
}

function scopeChanged() {
  if (options.value && filters.game_type && !typeOptions.value.some(t => t.key === filters.game_type)) {
    filters.game_type = '';
  }
}
function commitSpace({ year, platforms, genres, modes }) {
  filters.year = year;
  filters.platform_ids = platforms;
  filters.platform_id = '';
  filters.genre_ids = genres; filters.genre_id = '';
  filters.mode_ids = modes; filters.mode_id = '';
  filterChanged();
}
filterSpace.retry = loadOptions;
function apply() {
  filtersOpen.value = false;
  if (!filters.q.trim() && hasSearch.value) return clearSearch();
  if (filters.q.trim() && !hasSearch.value && !browseState.value) {
    browseState.value = makeBrowseState(committed.value, currentPage.value, {
      left: window.scrollX, top: window.scrollY,
    });
  }
  const query = buildCatalogQuery(filters, 1, browseState.value);
  if (JSON.stringify(query) === JSON.stringify(route.query)) loadList();
  else router.push({ name: "catalog", query });
}
function searchScopeChanged(event) {
  filters.search_scope = event.target.value;
  if (hasSearch.value) apply();
}
function scopeClicked(event) {
  // Let native radio activation (including arrow keys) update checked state.
  // Pointer clicks on the visible label toggle even when it is already selected.
  if (event.target?.tagName === "INPUT") return;
  event.preventDefault();
  filters.search_scope = filters.search_scope === "global" ? "filtered" : "global";
  if (hasSearch.value) apply();
}
function filterChanged() {
  if (hasSearch.value) {
    filters.search_scope = "filtered";
  }
}
function applyFilters() {
  if (filters.q.trim()) filters.search_scope = "filtered";
  apply();
}
function searchInputChanged(event) {
  stopSearchDissolve();
  if (!event.target.value.trim() && hasSearch.value) clearSearch();
}
function clearSearchWithEffect() {
  stopSearchDissolve();
  try {
    stopSearchDissolve = dissolveSearchText(searchInput.value);
  } catch {
    // A decorative effect must never prevent clearing the real search.
    stopSearchDissolve = () => {};
  }
  clearSearch();
  searchInput.value?.focus({ preventScroll: true });
}
function clearSearch() {
  filters.q = "";
  if (!hasSearch.value) return;
  const saved = browseState.value ?? makeBrowseState(committed.value, 1);
  const target = { name: "catalog", query: buildQuery(saved.filters, saved.page) };
  catalogScroll.restoreOnNextCatalog(router.resolve(target).fullPath, saved.position);
  router.push(target);
}
function reset() {
  Object.assign(filters, defaults());
  browseState.value = null;
  filtersOpen.value = false;
  if (!Object.keys(route.query).length) loadList();
  else router.push({ name: "catalog", query: {} });
}
function goPage(page) {
  router.push({ name: "catalog", query: buildCatalogQuery(committed.value, page, browseState.value) });
  document.getElementById("results-title")?.scrollIntoView({ block: "start" });
}
watch(() => route.query, () => loadList(!catalogReady.value), { immediate: true });
watch(catalogDataVersion, (next, previous) => {
  if (shouldRefreshCatalog(previous, next)) {
    loadList();
    loadOptions();
  }
});
loadOptions(true);
watch([listReady,optionsReady], async ([list,dict]) => {
  if (!alive || catalogReady.value || !list || !dict) return;
  catalogReady.value = true;
  await nextTick();
  if (alive) catalogScroll.catalogReady(route.fullPath);
});
function retryPreparation() {
  if (loading.value || filterSpace.state.loading) return;
  if (!listReady.value) loadList(true);
  if (!optionsReady.value) loadOptions(true);
}
onBeforeUnmount(() => {
  alive = false;
  stopSearchDissolve();
  listController?.abort();
});
</script>

<template>
  <div v-if="!catalogReady" class="catalog-preparation" :aria-busy="loading || filterSpace.state.loading">
    <p v-if="loading || filterSpace.state.loading" role="status">正在准备游戏资料库…</p>
    <div v-else role="alert"><p>{{ optionError || error || '暂时无法准备游戏资料库。' }}</p><button type="button" @click="retryPreparation">重试</button></div>
  </div>
  <div v-else class="page-shell">
    <form class="search-form" method="get" action="#/" @submit.prevent="apply">
      <label class="sr-only" for="search">搜索游戏名称</label>
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </svg>
      <div class="search-entry">
      <input
        ref="searchInput"
        id="search"
        v-model="filters.q"
        name="q"
        type="search"
        maxlength="100"
        placeholder="搜索游戏"
        autocomplete="off"
        enterkeyhint="search"
        @input="searchInputChanged"
      />
      <button v-if="filters.q" class="text-button clear-search" type="button"
        aria-label="清除搜索内容" title="清除搜索内容" @click="clearSearchWithEffect">
        <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m7 7 10 10M17 7 7 17" /></svg>
      </button>
      </div>
      <fieldset class="search-scope" :class="{ 'covers-global': filters.search_scope === 'filtered' }">
        <legend class="sr-only">搜索范围</legend>
        <label v-for="mode in [
          { value: 'global', label: '全库搜索' },
          { value: 'filtered', label: '筛选内搜索' },
        ]" :key="mode.value" :for="`search-scope-${mode.value}`" class="scope-choice"
          @click="scopeClicked">
          <input :id="`search-scope-${mode.value}`" class="sr-only" type="radio"
            name="search_scope" :value="mode.value"
            :checked="filters.search_scope === mode.value" @change="searchScopeChanged" />
          <span>{{ mode.label }}</span>
        </label>
        <span class="scope-cover" aria-hidden="true"></span>
      </fieldset>
      <button class="primary" type="submit">搜索游戏</button>
    </form>
    <span v-if="globalSearch" id="global-filter-hint" class="sr-only">左侧筛选暂未参与搜索，应用筛选后切换为筛选内搜索。</span>
    <div class="catalog-layout">
      <aside class="filter-sidebar">
        <button
          type="button"
          class="filter-toggle"
          :aria-expanded="filtersOpen"
          aria-controls="filters-panel"
          @click="filtersOpen = !filtersOpen"
        >
          筛选条件 <span>{{ filtersOpen ? "收起 −" : "展开 ＋" }}</span>
        </button>
        <form
          id="filters-panel"
          class="filters-panel"
          :class="{ 'is-open': filtersOpen, 'filters-inactive': globalSearch }"
          :aria-describedby="globalSearch ? 'global-filter-hint' : undefined"
          method="get"
          action="#/"
          @submit.prevent="applyFilters"
          @change="filterChanged"
        >
          <div class="panel-heading">
            <div class="filter-panel-title">
              <h2>筛选条件</h2>
              <FilterHelp />
            </div>
            <button type="button" class="text-button" @click="reset">
              重置
            </button>
          </div>
          <div v-if="optionError" class="inline-error" role="alert">
            {{ optionError }}
            <button type="button" class="text-button" @click="loadOptions">
              重试
            </button>
          </div>
          <fieldset>
            <legend>发售年份</legend>
            <YearPicker
              id="year"
              v-model="filters.year"
              :years="yearOptions"
              @change="filterChanged"
            />
          </fieldset>
          <fieldset class="scope-options">
            <legend>收录范围</legend>
            <label
              v-for="s in [
                {
                  value: 'default',
                  name: '主要游戏',
                },
                {
                  value: 'all',
                  name: '全部条目',
                },
                {
                  value: 'unknown',
                  name: '待分类',
                },
              ]"
              :key="s.value"
              ><input
                v-model="filters.scope"
                type="radio"
                name="scope"
                :value="s.value"
                @change="scopeChanged"
              /><span>{{ s.name }}</span></label
            >
          </fieldset>
          <fieldset>
            <legend>条目类别</legend>
            <label class="sr-only" for="game-type">条目类别</label
            ><select
              id="game-type"
              v-model="filters.game_type"
              name="game_type"
            >
              <option value="">当前范围全部类别</option>
              <option
                v-for="type in typeOptions"
                :key="type.key"
                :value="type.key"
              >
                {{ type.label }}
              </option>
            </select>
          </fieldset>
          <fieldset>
            <legend>游戏平台</legend>
            <PlatformPicker id="platform" :platforms="options?.platforms ?? []"
              :model-value="[filters.platform_ids, filters.platform_id].filter(Boolean).join(',')"
              @update:model-value="filters.platform_ids = $event; filters.platform_id = ''"
              @change="filterChanged" />
          </fieldset>
          <fieldset>
            <legend>玩法类型</legend>
            <GenrePicker id="genre" :genres="options?.genres ?? []" v-model="filters.genre_ids" @change="filterChanged" />
          </fieldset>
          <fieldset>
            <legend>游玩模式</legend>
            <ModePicker id="mode" :modes="options?.game_modes ?? []" v-model="filters.mode_ids" @change="filterChanged" />
          </fieldset>
          <fieldset class="rating-fields">
            <legend>用户评分</legend>
            <div class="field">
              <label for="min-rating">最低评分</label
              ><input
                id="min-rating"
                v-model="filters.min_rating"
                name="min_rating"
                type="number"
                min="0"
                max="100"
                step="0.1"
                placeholder="不限"
              />
            </div>
            <div class="field">
              <label for="min-count">最低用户评分人数</label
              ><input
                id="min-count"
                v-model="filters.min_rating_count"
                name="min_rating_count"
                type="number"
                min="0"
                max="2147483647"
                step="1"
                placeholder="不限"
              />
            </div>
          </fieldset>
          <button class="primary apply-button" type="submit">应用筛选</button>
        </form>
      </aside>
      <section
        class="results-section"
        :aria-busy="loading"
        aria-labelledby="results-title"
      >
        <div class="results-heading">
          <div>
            <h1 id="results-title">
              游戏目录
              <span>{{
                loading ? "查询中…" : `${number(result?.total)} 款`
              }}</span>
            </h1>
          </div>
          <div class="sort-control">
            <label for="sort">排序</label
            ><select
              id="sort"
              v-model="filters.sort"
              name="sort"
              @change="apply"
            >
              <option value="release_desc">发售日期 · 从新到旧</option>
              <option value="release_asc">发售日期 · 从旧到新</option>
              <option value="rating_desc">用户评分 · 从高到低</option>
              <option value="rating_asc">用户评分 · 从低到高</option>
              <option value="name_asc">游戏名称 · A–Z</option>
            </select>
          </div>
        </div>
        <div class="selection-clear-space" aria-hidden="true"></div>
        <div v-if="error" class="empty-state error-state" role="alert">
          <span aria-hidden="true">!</span>
          <h3>暂时无法加载游戏</h3>
          <p>{{ error }}</p>
          <button type="button" class="primary" @click="loadList">
            重新加载
          </button>
        </div>
        <div
          v-else-if="loading"
          class="game-grid skeleton-grid"
          aria-label="正在加载游戏"
        >
          <div v-for="n in 8" :key="n" class="skeleton-card">
            <div></div>
            <span></span><span></span>
          </div>
        </div>
        <div v-else-if="!result?.items.length" class="empty-state">
          <span aria-hidden="true">⌕</span>
          <h3>
            {{ result?.total ? "这一页没有游戏" : "没有找到符合条件的游戏" }}
          </h3>
          <p>{{ globalSearch ? "试试更换游戏名称或缩短关键词。" : "试试更换关键词，或放宽平台与评分条件。" }}</p>
          <button
            type="button"
            class="primary"
            @click="result?.total ? goPage(1) : globalSearch ? clearSearch() : reset()"
          >
            {{ result?.total ? "返回第一页" : globalSearch ? "返回浏览" : "重置筛选" }}
          </button>
        </div>
        <div v-else class="game-grid"
          @pointerdown="startCardSelection"
          @pointercancel="cardPointerStart = null"
          @click.capture="guardCardSelection"
        >
          <RouterLink
            v-for="game in result.items"
            :key="game.igdb_id"
            :to="{
              name: 'detail',
              params: { id: game.igdb_id },
              query: route.query,
            }"
            class="game-card"
            :draggable="false"
          >
            <div class="card-cover">
              <CoverImage :url="game.cover_url" :name="game.name" />
            </div>
            <div class="card-content">
              <h3>{{ game.name }}</h3>
              <p class="card-platforms">
                {{ game.game_type_label }} ·
                {{
                  game.platforms
                    .map((t) => t.name || `平台 ${t.id}`)
                    .join(" · ") || "暂无平台资料"
                }}
              </p>
              <div class="card-bottom">
                <time :datetime="game.first_release_date_utc">{{
                  game.first_release_date_utc
                }}</time
                ><span
                  class="card-score"
                  :class="{ unrated: game.rating === null }"
                  >{{
                    game.rating === null
                      ? "暂无评分"
                      : `评分 ${score(game.rating)}`
                  }}</span
                >
              </div>
            </div>
          </RouterLink>
        </div>
        <nav
          v-if="!loading && !error && result?.total_pages"
          class="pagination"
          aria-label="游戏列表分页"
        >
          <div class="pagination-controls">
            <button
              class="pagination-step"
              type="button"
              :disabled="currentPage <= 1"
              @click="goPage(currentPage - 1)"
            >上一页</button>
            <div class="pagination-pages">
              <template v-for="(page, i) in pageNumbers" :key="page">
                <span
                  v-if="i && page - pageNumbers[i - 1] > 1"
                  class="page-gap"
                  aria-hidden="true"
                >…</span>
                <button
                  type="button"
                  :class="{
                    current: page === currentPage,
                    'page-neighbor': page !== currentPage && page !== 1 && page !== result.total_pages,
                  }"
                  :aria-label="`第 ${page} 页`"
                  :aria-current="page === currentPage ? 'page' : undefined"
                  @click="goPage(page)"
                >{{ page }}</button>
              </template>
            </div>
            <button
              class="pagination-step"
              type="button"
              :disabled="!result.has_next"
              @click="goPage(currentPage + 1)"
            >下一页</button>
          </div>
          <PageJump
            :current-page="currentPage"
            :total-pages="result.total_pages"
            @jump="goPage"
          />
        </nav>
      </section>
    </div>
    <FilterSpace />
  </div>
</template>

<style scoped>
.catalog-preparation { min-height:55vh;display:grid;place-items:center;text-align:center;padding:32px;color:#a8b8ce; }
.catalog-preparation p { max-width:36em;margin:0 0 18px; }
.search-form {
  margin-bottom: 28px;
}
.search-entry {
  position: relative;
  flex: 1;
  min-width: 0;
}
.search-entry input {
  width: 100%;
  padding-right: 36px;
}
.search-entry input::-webkit-search-cancel-button {
  -webkit-appearance: none;
  appearance: none;
}
.search-entry.is-dissolving input::placeholder {
  color: transparent;
}
.search-entry .clear-search {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  min-height: 32px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  color: #a8b9d0;
  user-select: none;
}
.search-entry .clear-search:hover {
  background: #293443;
  color: #edf0f5;
}
.search-entry .clear-search svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.6;
  fill: none;
}
.search-scope {
  -webkit-user-select: none;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  position: relative;
  isolation: isolate;
  display: flex;
  flex: 0 0 230px;
  width: 230px;
  align-items: center;
  gap: 0;
  padding: 3px;
  margin: 0;
  min-width: 0;
  border: 1px solid #3b4759;
  border-radius: 8px;
  background: #141a23;
  overflow: hidden;
}
.scope-choice {
  position: relative;
  z-index: 1;
  flex: 1 1 0;
  min-width: 0;
  cursor: pointer;
}
.scope-choice span {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 12px;
  border-radius: 5px;
  color: #bac9dc;
  font-size: 0.9375rem;
  white-space: nowrap;
  transition: color 200ms ease, text-shadow 200ms ease;
}
.scope-choice span::before {
  content: "";
  position: absolute;
  z-index: -1;
  inset: 3px 4px;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgb(255 218 128 / 6%) 0%, rgb(255 202 88 / 2.5%) 48%, transparent 85%);
  opacity: 0;
  transition: opacity 200ms ease;
  pointer-events: none;
}
.search-scope input {
  width: 1px;
  min-height: 1px;
  height: 1px;
  padding: 0;
  margin: 0;
}
.scope-choice input:checked + span {
  color: #e6dcbc;
  font-weight: 600;
  text-shadow:
    0 0 1px rgb(255 250 232 / 32%),
    0 0 4px rgb(255 230 163 / 24%),
    0 0 10px rgb(255 211 106 / 22%),
    0 0 18px rgb(255 194 77 / 11%);
}
.scope-choice input:checked + span::before {
  opacity: 1;
}
.scope-cover {
  position: absolute;
  z-index: 2;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc((100% - 6px) / 2);
  border: 1px solid #48515d;
  border-radius: 5px;
  background: linear-gradient(180deg, #303844, #222933);
  box-shadow: 0 2px 5px rgb(0 0 0 / 28%), inset 0 1px 0 rgb(255 255 255 / 5%);
  transform: translateX(100%);
  transition: transform 200ms cubic-bezier(0.22, 0.68, 0, 1);
  pointer-events: none;
}
.search-scope.covers-global .scope-cover {
  transform: translateX(0);
}
.scope-choice input:focus-visible + span {
  outline: 2px solid #f1dfa0;
  outline-offset: -2px;
}
@media (prefers-reduced-motion: reduce) {
  .scope-cover,
  .scope-choice span,
  .scope-choice span::before {
    transition: none;
  }
}
.filters-inactive fieldset {
  opacity: 0.65;
}
.filters-inactive fieldset:focus-within,
.filters-inactive fieldset:hover {
  opacity: 1;
}
.filter-panel-title > h2,
.filters-panel legend,
.filters-panel label,
.filter-toggle,
.apply-button,
.search-form > .primary,
.results-heading h1,
.sort-control > label {
  -webkit-user-select: none;
  user-select: none;
}
.clear-search {
  flex-shrink: 0;
}
@media (max-width: 800px) {
  .search-form {
    display: grid;
    grid-template-columns: 21px minmax(0, 1fr) auto;
    gap: 8px;
  }
  .search-form > svg {
    grid-column: 1;
    grid-row: 1;
  }
  .search-form > .search-entry {
    grid-column: 2;
    grid-row: 1;
  }
  .search-form .primary {
    grid-column: 3;
    grid-row: 1;
    padding-inline: 12px;
  }
  .search-scope {
    grid-column: 1 / -1;
    grid-row: 2;
    width: auto;
  }
}
.pagination {
  justify-content: center;
  flex-wrap: wrap;
  gap: 16px;
}
.pagination .pagination-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
}
.pagination-pages {
  display: flex;
  align-items: center;
  gap: 4px;
}
.pagination button {
  height: 40px;
  min-height: 40px;
  padding: 0 10px;
  font-size: 1rem;
  font-weight: 400;
  background: transparent;
}
.pagination-pages button {
  min-width: 40px;
  border-color: transparent;
}
.pagination .pagination-pages button.current {
  border-color: #6e9fda;
  background: #29466d;
  color: #edf5ff;
  font-weight: 600;
}
.pagination button:hover:not(:disabled):not(.current) {
  background: #222e3e;
  border-color: #58718f;
}
.pagination .page-gap {
  min-width: 12px;
  text-align: center;
}
@media (max-width: 600px) {
  .pagination {
    flex-direction: column;
    gap: 12px;
  }
  .pagination .pagination-controls {
    gap: 6px;
  }
  .pagination-pages {
    gap: 3px;
  }
  .pagination button {
    padding-inline: 6px;
    font-size: 0.875rem;
  }
  .pagination-pages button {
    min-width: 28px;
  }
  .pagination .page-neighbor {
    display: none;
  }
  .pagination .page-gap {
    min-width: 8px;
  }
}
.filter-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
</style>
