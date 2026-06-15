"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str):
    """
    Called by Gradio when the user submits a query.
    Generator — yields (log, listing, outfit, fitcard) tuples so the log
    panel updates in real time while the agent runs.
    """
    # Guard: empty query
    if not user_query or not user_query.strip():
        yield "Please enter a search query.", "", "", ""
        return

    # Select wardrobe based on the radio button choice
    if wardrobe_choice == "Example wardrobe":
        wardrobe = get_example_wardrobe()
    else:
        wardrobe = get_empty_wardrobe()

    # Show "running..." immediately so the user knows something is happening
    yield "Running...", "", "", ""

    # Run the agent — this blocks until complete (all 3 LLM calls finish)
    session = run_agent(user_query, wardrobe)

    # Build the log text from the narration lines collected during the run
    log_text = "\n".join(session.get("log", []))

    # Error path — surface error in listing panel, log shows what happened
    if session["error"]:
        yield log_text, session["error"], "", ""
        return

    # Format the top listing dict into a readable string for panel 1
    item = session["selected_item"]
    listing_text = (
        f"{item['title']}\n"
        f"Price:     ${item['price']:.2f}\n"
        f"Platform:  {item['platform']}\n"
        f"Size:      {item['size']}\n"
        f"Condition: {item['condition']}\n"
        f"Category:  {item['category']}\n"
        f"Style:     {', '.join(item['style_tags'])}\n"
        f"Colors:    {', '.join(item['colors'])}\n"
        + (f"Brand:     {item['brand']}\n" if item.get("brand") else "")
    )

    yield log_text, listing_text, session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        # Agent log panel — shows step-by-step narration of what the agent did
        log_output = gr.Textbox(
            label="Agent log",
            lines=12,
            interactive=False,
        )

        with gr.Row():
            listing_output = gr.Textbox(
                label="Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        outputs = [log_output, listing_output, outfit_output, fitcard_output]

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
