// Redux store built with Redux Toolkit
import { configureStore } from "@reduxjs/toolkit";
import fixturesReducer from "../features/fixtures/fixturesSlice.js";
export const store = configureStore({
  reducer: { fixtures: fixturesReducer }, // state.fixtures holds the fixture list
});