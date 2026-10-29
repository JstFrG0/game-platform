import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import CatalogPage from "./pages/CatalogPage.vue";
import DetailPage from "./pages/DetailPage.vue";
import { catalogScroll } from "./catalogScroll.js";
import "./style.css";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "catalog", component: CatalogPage },
    { path: "/games/:id", name: "detail", component: DetailPage },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: catalogScroll.scrollBehavior,
});

router.beforeEach((to, from) => {
  catalogScroll.beforeNavigation(to, from, {
    left: window.scrollX,
    top: window.scrollY,
  });
});

createApp(App).use(router).mount("#app");
