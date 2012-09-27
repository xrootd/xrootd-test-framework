$(function() {
    $(document).ready(function() {
        main()
        $('html').show();
    });
});

// Content update ajax request. Only update pages with class "update".
if ($('#fixed-wrapper').hasClass('update')) {
    setInterval(function() {

        var anchors = new Array();
        $('a.current').each(function() {
            anchors.push($(this).attr('href'));
        });

        var postdata = {
            path : window.location.href
        };

        $.post('/update', postdata, function(data) {
            (document.getElementById("fixed-wrapper")).innerHTML = "";
            $('#fixed-wrapper').replaceWith(data);
            main(anchors);
        });
        return false;
    }, 1000);
}

function main(anchors) {

    // Notification Close Button
    $('.close-notification').click(function() {
        $(this).parent().fadeTo(350, 0, function() {
            $(this).slideUp(600);
        });
        return false;
    });

    // jQuery Tipsy
    $('[rel=tooltip], #main-nav span, .loader').tipsy({
        gravity : 's',
        fade : true
    }); // Tooltip Gravity Orientation: n | w | e | s

    // jQuery Facebox Modal
    $('.open-modal').nyroModal();

    // jQuery dataTables
    $('.datatable').dataTable();

    // Check all checkboxes
    $('.check-all').click(
            function() {
                $(this).parents('form').find('input:checkbox').attr('checked',
                        $(this).is(':checked'));
            })

    $('#main-nav li a.no-submenu, #main-nav li li a').click(function() {
        window.location.href = (this.href); // Open link instead of a sub menu
        return false;
    });

    // Widget Close Button
    $('.close-widget').click(function() {
        $(this).parent().fadeTo(350, 0, function() {
            $(this).slideUp(600);
        });
        return false;
    });

    // Table actions
    $('.table-switch').hide();
    $('.toggle-table-switch').click(
            function() {
                $(this).parent().parent().siblings().find(
                        '.toggle-table-switch').removeClass('active').next()
                        .slideUp();
                $(this).toggleClass('active').next().slideToggle();
                $(document).click(function() {
                    $('.table-switch').slideUp();
                    $('.toggle-table-switch').removeClass('active')
                });
                return false;
            });

    // Tickets
    $('.tickets .ticket-details').hide();
    $('.tickets .ticket-open-details').click(
            function() {
                // $('.tickets .ticket-details').slideUp()
                $(this).parent().parent().parent().parent().siblings().find(
                        '.ticket-details').slideUp();
                $(this).parent().parent().parent().parent().find(
                        '.ticket-details').slideToggle();
                return false;
            });

    // Content box tabs and sidetabs
    $('.tab, .sidetab').hide();
    $('.default-tab, .default-sidetab').show();
    $('.tab-switch a.default-tab, .sidetab-switch a.default-sidetab').addClass(
            'current');

    if ($('#fixed-wrapper').hasClass('update')) {
        if (anchors instanceof Array) {
            var i;
            for (i = 0; i < anchors.length; i++) {

                $('.tab, .sidetab').hide();
                $(
                        '.tab-switch a.default-tab, .sidetab-switch a.default-sidetab')
                        .removeClass('current');

                $("a[href='" + anchors[i] + "']").addClass('current');
                $(anchors[i]).show();
            }
        }
    }

    if (window.location.hash && window.location.hash.match(/^#tab\d+/)) {
        var tabID = window.location.hash;

        $(".tab-switch a[href='" + tabID + "']").addClass('current').parent()
                .siblings().find('a').removeClass('current');
        $('div' + tabID).parent().find('.tab').hide();
        $('div' + tabID).show();
    } else if (window.location.hash
            && window.location.hash.match(/^#sidetab\d+/)) {
        var sidetabID = window.location.hash;

        $(".sidetab-switch a[href='" + sidetabID + "']").addClass('current');
        $('div' + sidetabID).parent().find('.sidetab').hide();
        $('div' + sidetabID).show();
    } else if (window.location.hash && window.location.hash.match(/^#tab.+/)) {
        var tabID = window.location.hash;

        $(".tab-switch a[href='" + tabID + "']").addClass('current');
        $('div' + sidetabID).parent().find('.sidetab').hide();
        $('div' + sidetabID).show();
    } else if (window.location.hash
            && window.location.hash.match(/^#sidetab.+/)) {
        var sidetabID = window.location.hash;

        $(".sidetab-switch a[href='" + sidetabID + "']").addClass('current');
        $('div' + sidetabID).parent().find('.sidetab').hide();
        $('div' + sidetabID).show();
    }

    $('.tab-switch a').click(function() {
        var tab = $(this).attr('href');
        $(this).parent().siblings().find('a').removeClass('current');
        $(this).addClass('current');
        $(tab).siblings('.tab').hide();
        $(tab).show();
        return false;
    });

    $('.sidetab-switch a').click(function() {
        var sidetab = $(this).attr('href');
        $(this).parent().siblings().find('a').removeClass('current');
        $(this).addClass('current');
        $(sidetab).siblings('.sidetab').hide();
        $(sidetab).show();
        return false;
    });

    // Content box accordions
    $('.accordion li div').hide();
    $('.accordion li:first-child div').show();
    $('.accordion .accordion-switch').click(function() {
        $(this).parent().siblings().find('div').slideUp();
        $(this).next().slideToggle();
        return false;
    });

    // Minimize Content Article
    $('article header h2').css({
        'cursor' : 's-resize'
    });
    $('article header h2').click(function() {
        $(this).parent().find('nav').toggle();
        $(this).parent().parent().find('section, footer').toggle();
    });

    // Progress bar animation
    $('.progress-bar').each(function() {
        var progress = $(this).children().width();
        $(this).children().css({
            'width' : 0
        }).animate({
            width : progress
        }, 3000);
    });

    // Log selection box
    $("form.log-select").change(function() {
        var newloggroup = $(this).find('select option:selected').val()

        var refprefix = newloggroup.split('-').slice(0, -1).join('-');

        var oldrefs = new Array();
        $("a[href*='" + refprefix + "']").each(function(index) {
            oldrefs[index] = $(this).attr('href');
        })

        var newids = $("[id^='" + newloggroup + "']");
        $(newids).each(function(index) {
            var newref = '#' + $(this).attr('id');

            $("a[href='" + oldrefs[index] + "']").removeClass("current");
            $("a[href='" + oldrefs[index] + "']").attr('href', newref);
            $(oldrefs[index]).hide();
        });

        $("[id^='" + newloggroup + "'].default-log ").show();
        $("a[href*='" + newloggroup + "'].default-tab ").addClass("current");

    });

    $('[id^="imgselect-"]').each(function() {
        $(this).ddslick({
            width: 409,
            onSelected: function(data){
                $('#' + data.selectedData.value).siblings('.tab').hide();
                $('#' + data.selectedData.value).show();
            }
        });
    });
}
