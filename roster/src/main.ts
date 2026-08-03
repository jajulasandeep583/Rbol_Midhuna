import "./index.css";

import { createApp } from "vue";
import router from "./router";
import App from "./App.vue";

import { Button, setConfig, frappeRequest, resourcesPlugin } from "frappe-ui";
import { keepDropdownsInViewport } from "./utils/dropdownFit";

const app = createApp(App);

keepDropdownsInViewport();

setConfig("resourceFetcher", frappeRequest);

app.use(router);
app.use(resourcesPlugin);

app.component("Button", Button);
app.mount("#app");
