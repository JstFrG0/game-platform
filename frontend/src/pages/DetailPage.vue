<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import CoverImage from "../components/CoverImage.vue";
import IGNScoreBadge from "../components/IGNScoreBadge.vue";
import { request, score } from "../api.js";
import { catalogDataVersion } from "../dataVersion.js";
import { shouldRefreshCatalog } from "../dataUpdateStatus.js";
import { useBlankSelectionClear } from "../blankSelection.js";
useBlankSelectionClear();
const route = useRoute();
const game = ref(null),
  loading = ref(true),
  error = ref("");
let controller;
const back = computed(() => ({ name: "catalog", query: route.query }));
const ratingBlocks = computed(() =>
  game.value
    ? [
        {
          label: "IGDB 用户评分",
          value: game.value.rating,
          count: game.value.rating_count,
          unit: "人评分",
        },
        {
          label: "媒体汇总评分",
          value: game.value.aggregated_rating,
          count: game.value.aggregated_rating_count,
          unit: "个评分来源",
        },
        {
          label: "IGDB 综合评分",
          value: game.value.total_rating,
          count: game.value.total_rating_count,
          unit: "个评分",
        },
      ]
    : [],
);
const related = computed(() =>
  game.value
    ? [
        { label: "所属本体 / 合集", data: game.value.parent_game },
        { label: "版本对应游戏", data: game.value.version_parent },
      ].filter((r) => r.data)
    : [],
);
const reviewScope = (review) => {
  const scope = review.scope?.trim() || "";
  if (["", "一般评测", "普通评测"].includes(scope)) return "";
  return scope === "多人" ? "多人模式" : scope;
};
const companyRole = (c) =>
  [c.developer ? "开发" : "", c.publisher ? "发行" : ""]
    .filter(Boolean)
    .join(" / ") || "";
async function load() {
  controller?.abort();
  const current = (controller = new AbortController());
  loading.value = true;
  error.value = "";
  game.value = null;
  try {
    const data = await request(
      `games/${encodeURIComponent(route.params.id)}`,
      {},
      current.signal,
    );
    if (!current.signal.aborted) game.value = data;
  } catch (e) {
    if (
      !current.signal.aborted &&
      controller === current &&
      e.name !== "AbortError"
    )
      error.value = e.message;
  } finally {
    if (controller === current) loading.value = false;
  }
}
watch(() => route.params.id, load, { immediate: true });
watch(catalogDataVersion, (next, previous) => {
  if (shouldRefreshCatalog(previous, next)) load();
});
watch(game, (value) => {
  document.title = value ? `${value.name} · 游戏资料库` : "游戏资料库";
});
onBeforeUnmount(() => {
  controller?.abort();
  document.title = "游戏资料库";
});
</script>

<template>
  <div class="page-shell detail-shell">
    <div class="detail-toolbar">
      <RouterLink :to="back" class="back-link">← 返回目录</RouterLink>
      <a
        v-if="game?.igdb_url"
        :href="game.igdb_url"
        target="_blank"
        rel="noopener noreferrer"
        class="source-button"
        >IGDB ↗</a
      >
    </div>
    <div v-if="loading" class="detail-loading" role="status">正在加载…</div>
    <div v-else-if="error" class="empty-state error-state" role="alert">
      <h1>无法加载详情</h1>
      <p>{{ error }}</p>
      <button class="primary" type="button" @click="load">重试</button>
    </div>
    <article v-else-if="game">
      <section class="detail-hero" aria-labelledby="game-title">
        <div class="detail-cover">
          <CoverImage :url="game.cover_url" :name="game.name" eager />
        </div>
        <div class="detail-intro">
          <h1 id="game-title">{{ game.name }}</h1>
          <dl class="detail-facts">
            <div>
              <dt>类别</dt>
              <dd>
                {{ game.game_type_label
                }}<span v-if="game.version_title">
                  · {{ game.version_title }}</span
                >
              </dd>
            </div>
            <div>
              <dt>发售日期</dt>
              <dd>{{ game.first_release_date_utc }}</dd>
            </div>
            <div>
              <dt>平台</dt>
              <dd>
                {{
                  game.platforms
                    .map((t) => t.name || `平台 ${t.id}`)
                    .join(" · ") || "—"
                }}
              </dd>
            </div>
            <div>
              <dt>类型</dt>
              <dd>
                {{
                  game.genres
                    .map((t) => t.name || `类型 ${t.id}`)
                    .join(" · ") || "—"
                }}
              </dd>
            </div>
            <div>
              <dt>模式</dt>
              <dd>
                {{
                  game.game_modes
                    .map((t) => t.name || `模式 ${t.id}`)
                    .join(" · ") || "—"
                }}
              </dd>
            </div>
            <div v-if="game.companies.length">
              <dt>公司</dt>
              <dd>
                <span
                  v-for="(company, i) in game.companies"
                  :key="`${company.id}-${i}`"
                  >{{ i ? " · " : "" }}{{ company.name || `公司 ${company.id}`
                  }}<span v-if="companyRole(company)"
                    >（{{ companyRole(company) }}）</span
                  ></span
                >
              </dd>
            </div>
          </dl>
        </div>
      </section>
      <section class="detail-section" aria-labelledby="ratings-title">
        <h2 id="ratings-title">评分（100 分制）</h2>
        <div class="ratings-section">
          <div
            v-for="rating in ratingBlocks"
            :key="rating.label"
            class="rating-block"
          >
            <h3>{{ rating.label }}</h3>
            <div class="rating-value">
              <strong :class="{ 'no-score': rating.value === null }">{{
                score(rating.value)
              }}</strong
              ><span v-if="rating.value !== null && rating.count !== null"
                >{{ rating.count }} {{ rating.unit }}</span
              >
            </div>
          </div>
        </div>
      </section>
      <section
        v-if="game.ign_reviews?.length"
        class="detail-section"
        aria-labelledby="ign-title"
      >
        <h2 id="ign-title">IGN 评测（10 分制）</h2>
        <div class="ign-reviews">
          <div
            v-for="review in game.ign_reviews"
            :key="review.review_id"
            class="ign-review"
            :class="{ 'ign-review--general': !reviewScope(review) }"
          >
            <div v-if="reviewScope(review)" class="ign-review-content">
              <h3>{{ reviewScope(review) }}</h3>
              <p v-if="review.verdict" class="prose">{{ review.verdict }}</p>
            </div>
            <IGNScoreBadge :score="review.score" />
            <time v-if="review.review_date" :datetime="review.review_date">{{
              review.review_date
            }}</time>
            <a
              :href="review.review_url"
              target="_blank"
              rel="noopener noreferrer"
              >阅读评测 ↗</a
            >
          </div>
        </div>
      </section>
      <section class="detail-section">
        <h2>简介</h2>
        <p class="prose">{{ game.summary || "暂无简介。" }}</p>
      </section>
      <section v-if="game.storyline" class="detail-section">
        <h2>故事背景</h2>
        <p class="prose">{{ game.storyline }}</p>
      </section>
      <section v-if="related.length" class="detail-section">
        <h2>相关版本</h2>
        <div
          v-for="relation in related"
          :key="relation.label"
          class="related-row"
        >
          <span>{{ relation.label }}</span>
          <RouterLink
            v-if="relation.data.available_locally"
            :to="{
              name: 'detail',
              params: { id: relation.data.igdb_id },
              query: route.query,
            }"
            >{{ relation.data.name }} →</RouterLink
          >
          <span v-else>本地未收录 · ID {{ relation.data.igdb_id }}</span>
        </div>
      </section>
      <details class="extra-data">
        <summary>更多资料</summary>
        <dl class="detail-facts">
          <div v-if="game.alternative_names.length">
            <dt>别名</dt>
            <dd>{{ game.alternative_names.join(" / ") }}</dd>
          </div>
          <div>
            <dt>IGDB ID</dt>
            <dd>{{ game.igdb_id }}</dd>
          </div>
          <div>
            <dt>采集时间</dt>
            <dd>
              {{
                new Date(game.fetched_at).toLocaleString("zh-CN", {
                  hour12: false,
                })
              }}
            </dd>
          </div>
        </dl>
      </details>
    </article>
  </div>
</template>

<style scoped>
.ign-review--general > :first-child {
  grid-column: 2;
}
.ign-review--general time {
  white-space: nowrap;
}
</style>
