// Redux slice for fixtures: four async thunks and the reducers that update state
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { api } from "../../api/fixturesApi.js";
export const PAGE_SIZE = 20;
function errorText(err, fallback) {
  const detail = err.response?.data?.detail; // FastAPI puts the reason in "detail"
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; "); // 422 validation list
  return err.message ? `${fallback}: ${err.message}` : fallback; // network or server down
}
export const fetchFixtures = createAsyncThunk("fixtures/fetch", async (skip = 0, thunkAPI) => {
  try {
    const res = await api.get("/fixtures", { params: { skip, limit: PAGE_SIZE } }); // GET list
    return res.data;
  } catch (err) {
    return thunkAPI.rejectWithValue(errorText(err, "Failed to load fixtures"));
  }
});
export const createFixture = createAsyncThunk("fixtures/create", async (payload, thunkAPI) => {
  try {
    const res = await api.post("/fixtures", payload); // POST
    return res.data;
  } catch (err) {
    return thunkAPI.rejectWithValue(errorText(err, "Failed to create fixture"));
  }
});
export const updateFixture = createAsyncThunk("fixtures/update", async ({ id, changes }, thunkAPI) => {
  try {
    const res = await api.put(`/fixtures/${id}`, changes); // PUT /{id}
    return res.data;
  } catch (err) {
    return thunkAPI.rejectWithValue(errorText(err, "Failed to update fixture"));
  }
});
export const deleteFixture = createAsyncThunk("fixtures/delete", async (id, thunkAPI) => {
  try {
    await api.delete(`/fixtures/${id}`); // DELETE /{id}
    return id;
  } catch (err) {
    return thunkAPI.rejectWithValue(errorText(err, "Failed to delete fixture"));
  }
});
const fixturesSlice = createSlice({
  name: "fixtures",
  initialState: { items: [], skip: 0, loading: false, error: null },
  reducers: {
    clearError: (state) => { state.error = null; }, // hide the last error message
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchFixtures.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchFixtures.fulfilled, (state, action) => {
        state.loading = false;
        state.items = action.payload; // replace the list with the new page
        state.skip = action.meta.arg ?? 0; // remember which page is shown
      })
      .addCase(fetchFixtures.rejected, (state, action) => { state.loading = false; state.error = action.payload; })
      .addCase(createFixture.fulfilled, (state, action) => { state.items.unshift(action.payload); state.error = null; }) // newest first
      .addCase(createFixture.rejected, (state, action) => { state.error = action.payload; })
      .addCase(updateFixture.fulfilled, (state, action) => {
        const i = state.items.findIndex((f) => f.id === action.payload.id);
        if (i !== -1) state.items[i] = action.payload; // swap in the saved record
        state.error = null;
      })
      .addCase(updateFixture.rejected, (state, action) => { state.error = action.payload; })
      .addCase(deleteFixture.fulfilled, (state, action) => {
        state.items = state.items.filter((f) => f.id !== action.payload); // drop the deleted record
        state.error = null;
      })
      .addCase(deleteFixture.rejected, (state, action) => { state.error = action.payload; });
  },
});
export const { clearError } = fixturesSlice.actions;
export default fixturesSlice.reducer;