import { patch } from "@web/core/utils/patch";
import { SignatureForm } from "@portal/signature_form/signature_form";
import { addLoadingEffect } from "@web/core/utils/ui";
import { rpc } from "@web/core/network/rpc";
import { redirect } from "@web/core/utils/urls";

patch(SignatureForm.prototype, {
    async onClickSubmit() {
        const button = document.querySelector(".o_portal_sign_submit");
        const icon = button.removeChild(button.firstChild);
        const restoreBtnLoading = addLoadingEffect(button);

        const name = this.signature.name;
        const signature = this.signature.getSignatureImage().split(",")[1];
        const data = await rpc(this.props.callUrl, { name, signature });

        if (data.force_refresh) {
            restoreBtnLoading();
            button.prepend(icon);
            if (data.redirect_url) {
                redirect(data.redirect_url);
            } else {
                window.location.reload();
            }
            return new Promise(() => {});
        }

        // Restore button in both error and success cases
        restoreBtnLoading();
        button.prepend(icon);

        this.state.error = data.error || false;
        this.state.success = !data.error && {
            message: data.message,
            redirectUrl: data.redirect_url,
            redirectMessage: data.redirect_message,
        };
    },
});
